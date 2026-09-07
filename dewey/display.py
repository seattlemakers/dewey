"""ILI9341 LCD Display manager with black background and orange text UI."""

import logging
import textwrap
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont

try:
    import board
    import digitalio
    from adafruit_rgb_display import ili9341
except ImportError:
    board = None
    digitalio = None
    ili9341 = None

from dewey.config import (
    COLOR_BG,
    COLOR_DIM_TEXT,
    COLOR_TEXT,
    FONT_PATHS_BOLD,
    FONT_PATHS_NORMAL,
    FONT_SIZE_LARGE,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
    LCD_BAUDRATE,
    LCD_HEIGHT,
    LCD_ROTATION,
    LCD_WIDTH,
)

logger = logging.getLogger(__name__)


def _load_font(paths: List[str], size: int) -> ImageFont.ImageFont:
    """Loads a TTF font from a list of paths, falling back to default font."""
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow fallback where size argument is not accepted
        return ImageFont.load_default()


class DisplayManager:
    """Manages the ILI9341 TFT LCD screen and renders camera frames and UI screens."""

    def __init__(self):
        self.width = LCD_WIDTH
        self.height = LCD_HEIGHT
        self.disp = None

        # Load fonts
        self.font_large = _load_font(FONT_PATHS_BOLD, FONT_SIZE_LARGE)
        self.font_normal = _load_font(FONT_PATHS_NORMAL, FONT_SIZE_NORMAL)
        self.font_small = _load_font(FONT_PATHS_NORMAL, FONT_SIZE_SMALL)

        self._init_display()

    def _init_display(self) -> None:
        if None in (board, digitalio, ili9341):
            logger.warning("Adafruit CircuitPython/RGB Display libraries not available. Running in mock display mode.")
            return

        try:
            cs_pin = digitalio.DigitalInOut(board.CE0)
            dc_pin = digitalio.DigitalInOut(board.D25)
            # Hardware reset pin is NOT needed (software reset works fine; GPIO 24 reserved for keypad)
            spi = board.SPI()

            self.disp = ili9341.ILI9341(
                spi,
                rotation=LCD_ROTATION,
                cs=cs_pin,
                dc=dc_pin,
                rst=None,
                baudrate=LCD_BAUDRATE,
            )
            logger.info("ILI9341 display initialized successfully in landscape mode (%dx%d).", self.width, self.height)
        except Exception as err:
            logger.warning("Could not initialize ILI9341 display: %s (mock display mode)", err)
            self.disp = None

    def _present(self, img: Image.Image) -> None:
        """Pushes an image buffer directly to the display in native landscape orientation."""
        if not self.disp:
            return

        try:
            frame = img.resize((self.width, self.height), Image.Resampling.BILINEAR)
            self.disp.image(frame)
        except Exception as err:
            logger.error("Failed to render frame on display: %s", err)

    def show_camera_frame(self, frame: Image.Image) -> None:
        """Presents a live camera frame on the LCD.
        Camera hardware is mounted inverted relative to the screen;
        flip both axes so the camera stream is right-side up.
        """
        oriented_frame = frame.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
        self._present(oriented_frame)

    def show_status(self, title: str, message: str = "") -> None:
        """Displays an intermediate status/progress screen (e.g. Scanning/Analyzing)."""
        canvas = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"  # Monospace aliased printer aesthetic

        # Title (Large Orange text, centered)
        bbox = draw.textbbox((0, 0), title, font=self.font_large)
        title_w = bbox[2] - bbox[0]
        title_h = bbox[3] - bbox[1]
        draw.text(
            ((self.width - title_w) // 2, 70),
            title,
            font=self.font_large,
            fill=COLOR_TEXT,
        )

        # Message (Normal Orange text, centered)
        if message:
            bbox_m = draw.textbbox((0, 0), message, font=self.font_normal)
            msg_w = bbox_m[2] - bbox_m[0]
            draw.text(
                ((self.width - msg_w) // 2, 115),
                message,
                font=self.font_normal,
                fill=COLOR_TEXT,
            )

        # Subtle decorative border in dim orange
        draw.rectangle((6, 6, self.width - 7, self.height - 7), outline=COLOR_DIM_TEXT, width=1)
        self._present(canvas)

    @staticmethod
    def _wrap_value_lines(val: str, max_chars: int = 33, max_lines: int = 3) -> List[str]:
        """Wraps text cleanly across multiple lines, breaking on spaces or chunking long tokens."""
        val = (val or "").strip()
        if not val:
            return [""]

        words = val.split(" ")
        lines = []
        curr = ""

        for w in words:
            if not w:
                continue
            if len(w) > max_chars:
                if curr:
                    lines.append(curr)
                    curr = ""
                for i in range(0, len(w), max_chars):
                    chunk = w[i : i + max_chars]
                    if len(chunk) == max_chars:
                        lines.append(chunk)
                    else:
                        curr = chunk
                continue

            if not curr:
                curr = w
            elif len(curr) + 1 + len(w) <= max_chars:
                curr += " " + w
            else:
                lines.append(curr)
                curr = w

        if curr:
            lines.append(curr)

        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            if len(lines[-1]) > max_chars - 2:
                lines[-1] = lines[-1][: max_chars - 2] + ".."
            else:
                lines[-1] += ".."

        return lines or [""]

    def show_label_editor(
        self,
        fields: List[dict],
        selected_idx: int,
        is_editing: bool,
        edit_buffer: str = "",
        cursor_visible: bool = True,
    ) -> None:
        """Renders interactive label editor with monospace aliased typography:
        - Lists all editable label fields with automatic wrapping for Location, Category/Catalog, and Price
        - Highlights currently focused field (inverted block in browse mode, box in edit mode)
        - Shows inline edit controls (arrows for options, blinking cursor for text)
        - Context-sensitive button descriptions moved up one line with dual horizontal rule borders
        """
        canvas = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"  # Pure aliased 1-bit text rendering (printer style)

        margin_x = 8
        cur_y = 5

        # --- Top Header ---
        header_title = "[EDITING LABEL]" if is_editing else "[LABEL PREVIEW / EDIT]"
        draw.text((margin_x, cur_y), header_title, font=self.font_large, fill=COLOR_TEXT)

        cur_y += 20
        draw.line([(margin_x, cur_y), (self.width - margin_x, cur_y)], fill=COLOR_DIM_TEXT, width=1)
        start_y = cur_y + 4

        # Footer boundary: button descriptions moved up one line with lines above and under
        footer_y = self.height - 32
        max_y = footer_y - 6

        # --- Fields Layout with Multi-Line Wrapping ---
        # Allow location, category (human-readable catalog), price, and brief_desc to wrap
        wrappable_keys = {"location", "category", "price", "brief_desc"}
        max_chars_per_line = 33

        field_layouts = []
        for idx, field in enumerate(fields):
            is_selected = (idx == selected_idx)
            label_str = f"{field['label']:<8}"

            if is_selected and is_editing:
                if field.get("edit_display_str"):
                    val_str = field["edit_display_str"]
                elif field.get("type") == "choice":
                    val_str = f"◀ {field['val']} ▶"
                else:
                    cursor = "_" if cursor_visible else " "
                    val_str = f"{edit_buffer}{cursor}"
            else:
                val_str = str(field.get("val", ""))

            # Wrap field if requested or in wrappable keys
            if field.get("wrap", False) or field.get("key") in wrappable_keys:
                wrapped_vals = self._wrap_value_lines(val_str, max_chars=max_chars_per_line, max_lines=2)
                if len(wrapped_vals) == 1:
                    lines = [f"{label_str} {wrapped_vals[0]}"]
                else:
                    indent = " " * (len(label_str) + 1)
                    lines = [f"{label_str} {wrapped_vals[0]}"] + [f"{indent}{v}" for v in wrapped_vals[1:]]
            else:
                if len(val_str) > max_chars_per_line:
                    val_str = val_str[:max_chars_per_line - 2] + ".."
                lines = [f"{label_str} {val_str}"]

            # Dynamic field height: 16px base + 14px per extra line
            f_height = 16 + (len(lines) - 1) * 14
            field_layouts.append({"lines": lines, "height": f_height})

        # --- Dynamic Scrolling to keep selected_idx visible ---
        if not hasattr(self, "_editor_scroll_offset"):
            self._editor_scroll_offset = 0

        if selected_idx < self._editor_scroll_offset:
            self._editor_scroll_offset = selected_idx

        def span_h(start_i: int, end_i: int) -> int:
            return sum(field_layouts[k]["height"] for k in range(start_i, end_i + 1))

        avail_h = max_y - start_y
        while self._editor_scroll_offset < selected_idx and span_h(self._editor_scroll_offset, selected_idx) > avail_h:
            self._editor_scroll_offset += 1

        # --- Render Visible Fields ---
        draw_y = start_y
        last_drawn_idx = self._editor_scroll_offset

        for idx in range(self._editor_scroll_offset, len(fields)):
            layout = field_layouts[idx]
            flines = layout["lines"]
            fheight = layout["height"]

            if draw_y + fheight > max_y + 2 and idx != selected_idx:
                break

            last_drawn_idx = idx
            is_sel = (idx == selected_idx)

            if is_sel:
                if is_editing:
                    # Outlined box for active edit field
                    draw.rectangle(
                        [(margin_x - 2, draw_y - 1), (self.width - margin_x + 2, draw_y + fheight - 3)],
                        outline=COLOR_TEXT,
                        width=1,
                    )
                    for li, ltext in enumerate(flines):
                        draw.text((margin_x, draw_y + li * 14), ltext, font=self.font_normal, fill=COLOR_TEXT)
                else:
                    # Browse mode: full inverted orange block with black text
                    draw.rectangle(
                        [(margin_x - 2, draw_y - 1), (self.width - margin_x + 2, draw_y + fheight - 3)],
                        fill=COLOR_TEXT,
                    )
                    for li, ltext in enumerate(flines):
                        draw.text((margin_x, draw_y + li * 14), ltext, font=self.font_normal, fill=COLOR_BG)
            else:
                for li, ltext in enumerate(flines):
                    draw.text((margin_x, draw_y + li * 14), ltext, font=self.font_normal, fill=COLOR_TEXT)

            draw_y += fheight

        # Scroll indicators
        if self._editor_scroll_offset > 0:
            draw.text((self.width - margin_x - 10, cur_y - 18), "▲", font=self.font_small, fill=COLOR_DIM_TEXT)
        if last_drawn_idx < len(fields) - 1:
            draw.text((self.width - margin_x - 10, footer_y - 16), "▼", font=self.font_small, fill=COLOR_DIM_TEXT)

        # --- Footer: Button Descriptions with Top and Under Lines ---
        draw.line([(margin_x, footer_y - 4), (self.width - margin_x, footer_y - 4)], fill=COLOR_DIM_TEXT, width=1)

        if is_editing:
            cur_field = fields[selected_idx] if 0 <= selected_idx < len(fields) else {}
            if cur_field.get("footer_hint"):
                footer_text = cur_field["footer_hint"]
            elif cur_field.get("type") == "choice":
                footer_text = "F1/F2:Cycle  ENT:Select  CLR:Reset  ESC:Cancel"
            else:
                footer_text = "0-9/Keys:Type  F3/.:Dot  CLR:Clear  ENT:Save  ESC:Cancel"
        else:
            footer_text = "F1/F2:Move  ENT:Edit  PRINT/P:Print  F4/ESC:Camera"

        draw.text((margin_x, footer_y), footer_text, font=self.font_small, fill=COLOR_DIM_TEXT)
        draw.line([(margin_x, footer_y + 14), (self.width - margin_x, footer_y + 14)], fill=COLOR_DIM_TEXT, width=1)

        self._present(canvas)

    def show_component_result(
        self,
        part_number: str,
        description: str,
        comp_type: str = "",
        mfr_part_number: str = "",
        brief_desc: str = "",
        price: str = "",
    ) -> None:
        """Renders component identification result:
        - Component type badge (e.g. [BOB]) in inverted colors
        - Part number and optional manufacturer SKU
        - Brief description and price
        - Word-wrapped technical description
        - Footer showing available actions
        """
        canvas = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"  # Monospace aliased printer aesthetic

        margin_x = 10
        cur_y = 8

        # --- Top Header: Component Badge + Part Number ---
        font_pn = self.font_large
        x_pos = margin_x

        if comp_type:
            # Draw inverted badge: Orange rectangle with black text
            badge_text = f" {comp_type} "
            bbox_badge = draw.textbbox((0, 0), badge_text, font=self.font_normal)
            b_w = bbox_badge[2] - bbox_badge[0] + 6
            b_h = bbox_badge[3] - bbox_badge[1] + 6
            draw.rounded_rectangle([(x_pos, cur_y + 2), (x_pos + b_w, cur_y + 2 + b_h)], radius=3, fill=COLOR_TEXT)
            draw.text((x_pos + 3, cur_y + 4), badge_text, font=self.font_normal, fill=COLOR_BG)
            x_pos += b_w + 8

        # Main Part Number
        title_text = part_number
        if mfr_part_number:
            title_text = f"{part_number} {mfr_part_number}"

        bbox_pn = draw.textbbox((0, 0), title_text, font=font_pn)
        if (x_pos + (bbox_pn[2] - bbox_pn[0])) > (self.width - margin_x):
            font_pn = self.font_normal
            bbox_pn = draw.textbbox((0, 0), title_text, font=font_pn)

        draw.text((x_pos, cur_y), title_text, font=font_pn, fill=COLOR_TEXT)

        header_h = max(28, (bbox_pn[3] - bbox_pn[1]))
        cur_y += header_h + 6

        # Separator line
        draw.line([(margin_x, cur_y), (self.width - margin_x, cur_y)], fill=COLOR_DIM_TEXT, width=1)
        cur_y += 6

        # --- Subheader: Brief description / Price ---
        if brief_desc or price:
            sub_text = brief_desc
            if price and not sub_text.endswith(price):
                sub_text = f"{brief_desc} | {price}" if brief_desc else price
            for line in textwrap.wrap(sub_text, width=38)[:2]:
                draw.text((margin_x, cur_y), line, font=self.font_normal, fill=COLOR_TEXT)
                cur_y += 18
            cur_y += 2

        # --- Body: Technical Description ---
        desc_lines = textwrap.wrap(description, width=40)
        remaining_h = (self.height - 24) - cur_y
        max_lines = max(1, remaining_h // 16)

        for line in desc_lines[:max_lines]:
            draw.text((margin_x, cur_y), line, font=self.font_small, fill=COLOR_TEXT)
            cur_y += 15

        if len(desc_lines) > max_lines:
            draw.text((margin_x, cur_y), "...", font=self.font_small, fill=COLOR_DIM_TEXT)

        # --- Footer: Controls Hint ---
        footer_y = self.height - 32
        draw.line([(margin_x, footer_y - 4), (self.width - margin_x, footer_y - 4)], fill=COLOR_DIM_TEXT, width=1)
        footer_text = "[PRINT] Print Label   [F4] Live View   [SCAN] Rescan"
        bbox_f = draw.textbbox((0, 0), footer_text, font=self.font_small)
        foot_w = bbox_f[2] - bbox_f[0]
        draw.text(
            ((self.width - foot_w) // 2, footer_y),
            footer_text,
            font=self.font_small,
            fill=COLOR_DIM_TEXT,
        )
        draw.line([(margin_x, footer_y + 14), (self.width - margin_x, footer_y + 14)], fill=COLOR_DIM_TEXT, width=1)

        self._present(canvas)

    def show_error(self, title: str, message: str) -> None:
        """Renders an error screen with recovery hint."""
        canvas = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"  # Monospace aliased printer aesthetic

        draw.text((12, 20), f"ERROR: {title}", font=self.font_large, fill=COLOR_TEXT)
        draw.line([(12, 50), (self.width - 12, 50)], fill=COLOR_DIM_TEXT, width=1)

        lines = textwrap.wrap(message, width=38)
        cur_y = 60
        for line in lines[:6]:
            draw.text((12, cur_y), line, font=self.font_normal, fill=COLOR_TEXT)
            cur_y += 18

        draw.text(
            (12, self.height - 22),
            "Press [F4] to return or [SCAN] to retry",
            font=self.font_small,
            fill=COLOR_DIM_TEXT,
        )
        self._present(canvas)

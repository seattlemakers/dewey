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

    def show_component_result(self, part_number: str, description: str) -> None:
        """Renders component identification result:
        - Full black background
        - Part number at top in large orange text
        - Description below in normal size orange text
        - Footer showing available actions
        """
        canvas = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(canvas)

        # --- Top Header: Part Number ---
        margin_x = 12
        header_y = 10

        # Adjust font size if part number is exceptionally long
        font_pn = self.font_large
        bbox_pn = draw.textbbox((0, 0), part_number, font=font_pn)
        pn_w = bbox_pn[2] - bbox_pn[0]
        if pn_w > (self.width - 24):
            font_pn = self.font_normal
            bbox_pn = draw.textbbox((0, 0), part_number, font=font_pn)

        draw.text((margin_x, header_y), part_number, font=font_pn, fill=COLOR_TEXT)

        # Separator line
        sep_y = header_y + (bbox_pn[3] - bbox_pn[1]) + 8
        draw.line([(margin_x, sep_y), (self.width - margin_x, sep_y)], fill=COLOR_DIM_TEXT, width=1)

        # --- Body: Description ---
        # Wrap description to ~38 characters per line to fit 320px width cleanly
        desc_lines = textwrap.wrap(description, width=38)
        max_lines = 8  # Limit lines to prevent overflowing bottom footer
        cur_y = sep_y + 8

        for i, line in enumerate(desc_lines[:max_lines]):
            draw.text((margin_x, cur_y), line, font=self.font_normal, fill=COLOR_TEXT)
            cur_y += 18

        if len(desc_lines) > max_lines:
            draw.text((margin_x, cur_y), "...", font=self.font_normal, fill=COLOR_DIM_TEXT)

        # --- Footer: Controls Hint ---
        footer_text = "[PRINT] Print Label   [F4] Live View   [SCAN] Rescan"
        bbox_f = draw.textbbox((0, 0), footer_text, font=self.font_small)
        foot_w = bbox_f[2] - bbox_f[0]
        draw.text(
            ((self.width - foot_w) // 2, self.height - 18),
            footer_text,
            font=self.font_small,
            fill=COLOR_DIM_TEXT,
        )

        self._present(canvas)

    def show_error(self, title: str, message: str) -> None:
        """Renders an error screen with recovery hint."""
        canvas = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(canvas)

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

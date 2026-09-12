"""Thermal printer driver for Dewey legacy ESC/POS printer (v2.16 firmware)."""

import logging
import textwrap
import time
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

try:
    import serial
except ImportError:
    serial = None

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from dewey.config import (
    FONT_PATHS_BOLD,
    FONT_PATHS_NORMAL,
    PRINTER_BAUDRATE,
    PRINTER_BREAK_TIME,
    PRINTER_CHARS_PER_LINE,
    PRINTER_DENSITY,
    PRINTER_DOTS_PER_LINE,
    PRINTER_DTR_PIN,
    PRINTER_HEAT_DOTS,
    PRINTER_HEAT_INTERVAL,
    PRINTER_HEAT_TIME,
    PRINTER_LABEL_MODE,
    PRINTER_PORT,
    PRINTER_USE_DEFAULT_SETTINGS,
)

logger = logging.getLogger(__name__)


class LegacyThermalPrinter:
    """Driver for DFRobot Embedded Thermal Printer V2.0 (DFR0503-EN) and ESC/POS thermal printers."""

    def __init__(
        self,
        port: str = PRINTER_PORT,
        baudrate: int = PRINTER_BAUDRATE,
        timeout: float = 1.0,
        dtr_pin: Optional[int] = PRINTER_DTR_PIN,
        use_default_settings: bool = PRINTER_USE_DEFAULT_SETTINGS,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.dtr_pin = dtr_pin
        self.use_default_settings = use_default_settings
        self.ser: Optional["serial.Serial"] = None
        self._setup_dtr()
        self._connect()

    def _setup_dtr(self) -> None:
        """Configure the DTR GPIO pin as an input with pull-up, if available."""
        if self.dtr_pin is None or GPIO is None:
            if self.dtr_pin is not None and GPIO is None:
                logger.warning("RPi.GPIO not available — DTR flow control disabled.")
            return
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.dtr_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            logger.info("DTR flow control enabled on BCM GPIO %d.", self.dtr_pin)
        except Exception as err:
            logger.warning("Could not configure DTR pin %d: %s — DTR disabled.", self.dtr_pin, err)
            self.dtr_pin = None

    def _wait_for_ready(self, timeout: float = 3.0) -> None:
        """Block until the printer signals ready (DTR LOW) or timeout expires.

        The printer pulls DTR LOW when its buffer has room and HIGH when full.
        If DTR is not configured, this is a no-op.
        """
        if self.dtr_pin is None or GPIO is None:
            return
        import time as _time
        deadline = _time.monotonic() + timeout
        while GPIO.input(self.dtr_pin) == GPIO.HIGH:
            if _time.monotonic() >= deadline:
                logger.warning("DTR wait timed out after %.1fs — sending anyway.", timeout)
                return
            _time.sleep(0.001)

    def _connect(self) -> None:
        if serial is None:
            logger.warning("pyserial is not installed. Running in mock printer mode.")
            return

        try:
            self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
            time.sleep(0.3)
            self.reset()
            logger.info("Thermal printer connected on %s at %d baud (use_default_settings=%s).",
                        self.port, self.baudrate, self.use_default_settings)
        except Exception as err:
            logger.warning("Could not open thermal printer on %s: %s (mock mode active)", self.port, err)
            self.ser = None

    def reset(self) -> None:
        """Resets printer memory settings to factory defaults using ESC @."""
        if self.ser:
            self.ser.write(b'\x1b\x40')
            self.ser.flush()
            # Microcontroller needs 250ms to cold boot and reinitialize
            time.sleep(0.25)
        if not self.use_default_settings:
            # Apply legacy custom heating parameters only when explicitly configured
            self.set_heat_config()
            self.set_print_density()
        else:
            logger.info("[PRINTER] Using printer default settings (ESC @ applied).")

    def set_heat_config(
        self,
        dots: int = PRINTER_HEAT_DOTS,
        heat_time: int = PRINTER_HEAT_TIME,
        interval: int = PRINTER_HEAT_INTERVAL,
        force: bool = False,
    ) -> None:
        """Sets heating control parameters (ESC 7 n1 n2 n3) for legacy printers.
        Skipped if use_default_settings is True unless force=True.
        """
        if self.use_default_settings and not force:
            logger.debug("[PRINTER] Skipping ESC 7 (using printer default settings).")
            return
        logger.info("[PRINTER] ESC 7 applied: dots=%d ((n1+1)*8=%d), heat_time=%d (%dµs), interval=%d (%dµs)",
                    dots, (dots + 1) * 8, heat_time, heat_time * 10, interval, interval * 10)
        if self.ser:
            cmd = b'\x1b\x37' + bytes([dots & 0xFF, heat_time & 0xFF, interval & 0xFF])
            self._wait_for_ready()
            self.ser.write(cmd)
            self.ser.flush()
            time.sleep(0.05)
        else:
            logger.info("[PRINTER MOCK] set_heat_config(dots=%d, time=%d, interval=%d)", dots, heat_time, interval)

    def set_print_density(
        self,
        density: int = PRINTER_DENSITY,
        break_time: int = PRINTER_BREAK_TIME,
        force: bool = False,
    ) -> None:
        """Sets print darkness density and break time (DC2 # n) for legacy printers.
        Skipped if use_default_settings is True unless force=True.
        """
        if self.use_default_settings and not force:
            logger.debug("[PRINTER] Skipping DC2 # (using printer default settings).")
            return
        val = ((break_time & 0x07) << 5) | (density & 0x1F)
        logger.info("[PRINTER] DC2 # applied: density=%d (%d%%), break_time=%d (%dµs), raw=0x%02X",
                    density, 50 + 5 * density, break_time, break_time * 250, val)
        if self.ser:
            cmd = b'\x12\x23' + bytes([val])
            self._wait_for_ready()
            self.ser.write(cmd)
            self.ser.flush()
            time.sleep(0.05)
        else:
            logger.info("[PRINTER MOCK] set_print_density(density=%d, break_time=%d)", density, break_time)

    def set_double_strike(self, enabled: bool = True) -> None:
        """Turns double-strike mode on or off (ESC G n) for even darker text."""
        if self.ser:
            val = b'\x01' if enabled else b'\x00'
            self._wait_for_ready()
            self.ser.write(b'\x1b\x47' + val)
        else:
            logger.info("[PRINTER MOCK] set_double_strike(%s)", enabled)

    def write(self, text: str) -> None:
        """Sends raw string text encoded in ASCII/CP437 without trailing newline."""
        if self.ser:
            self.ser.write(text.encode('ascii', errors='ignore'))
            self.ser.flush()
        else:
            logger.info("[PRINTER MOCK WRITE] %s", text)

    def write_line(self, text: str) -> None:
        """Prints a string line encoded in ASCII/CP437 layout."""
        if self.ser:
            self.ser.write(text.encode('ascii', errors='ignore') + b'\n')
            self.ser.flush()
            time.sleep(0.04)
        else:
            logger.info("[PRINTER MOCK] %s", text)

    def feed(self, lines: int = 1) -> None:
        """Feeds the paper by a specified number of lines."""
        if self.ser:
            for _ in range(lines):
                self._wait_for_ready()
                self.ser.write(b'\n')
                time.sleep(0.04)
            self.ser.flush()
        else:
            logger.info("[PRINTER MOCK FEED %d lines]", lines)

    # --- BITMAP / RASTER PRINTING ---

    def print_bitmap(self, image: "Image.Image", method: str = "raster") -> None:
        """Sends a PIL image to the thermal printer.

        Supported methods:
          - 'raster' (default): Native ESC/POS GS v 0 raster bit-image mode (A29).
            High-speed, line-accurate, supported natively by DFRobot Embedded Thermal Printer V2.0.
          - 'column': Legacy ESC * 24-dot column bit-image mode.
        """
        if Image is None:
            logger.warning("Pillow not installed — cannot print bitmap.")
            return

        bw = image.convert('1')
        w, h = bw.size
        pixels = bw.load()

        if not self.ser:
            logger.info("[PRINTER MOCK BITMAP (%s)] %dx%d px", method, w, h)
            return

        if not self.use_default_settings:
            self.set_heat_config()

        if method == "raster":
            # Native ESC/POS GS v 0 raster bit-image mode (1D 76 30 00 xL xH yL yH d1...dk)
            # xL, xH: number of horizontal bytes (width in dots / 8)
            # yL, yH: number of vertical dots (chunk height)
            x_bytes = (w + 7) // 8
            CHUNK_H = 128  # Transmit in 128-row chunks for smooth printing & buffer safety

            for y0 in range(0, h, CHUNK_H):
                strip_h = min(CHUNK_H, h - y0)
                raw = bytearray()
                for y in range(y0, y0 + strip_h):
                    for xb in range(x_bytes):
                        byte_val = 0
                        x_base = xb * 8
                        for bit in range(8):
                            x = x_base + bit
                            # In PIL '1': 0 = black (print dot), 255 = white
                            if x < w and pixels[x, y] == 0:
                                byte_val |= (0x80 >> bit)
                        raw.append(byte_val)

                xL = x_bytes & 0xFF
                xH = (x_bytes >> 8) & 0xFF
                yL = strip_h & 0xFF
                yH = (strip_h >> 8) & 0xFF
                cmd = b'\x1d\x76\x30\x00' + bytes([xL, xH, yL, yH]) + bytes(raw)
                self._wait_for_ready()
                self.ser.write(cmd)
                self.ser.flush()
                # Inter-chunk pacing
                time.sleep(0.08)
            return

        # Fallback: legacy ESC * 24-dot column bit-image mode
        self.ser.write(b'\x1b\x33\x18')  # ESC 3 24
        self.ser.flush()

        for y0 in range(0, h, 24):
            strip_h = min(24, h - y0)

            col_data = bytearray()
            for x in range(w):
                b0 = b1 = b2 = 0
                for row in range(strip_h):
                    y = y0 + row
                    if pixels[x, y] == 0:
                        if row < 8:
                            b0 |= (0x80 >> row)
                        elif row < 16:
                            b1 |= (0x80 >> (row - 8))
                        else:
                            b2 |= (0x80 >> (row - 16))
                col_data += bytes([b0, b1, b2])

            nL = w & 0xFF
            nH = (w >> 8) & 0xFF
            strip_packet = b'\x1b\x2a\x21' + bytes([nL, nH]) + bytes(col_data) + b'\n'
            self.ser.write(strip_packet)
            self.ser.flush()
            time.sleep(0.35)

        self.ser.write(b'\x1b\x32')  # ESC 2
        self.ser.flush()

    def render_label_image(
        self,
        part_number: str,
        description: str,
        dot_width: int = PRINTER_DOTS_PER_LINE,
    ) -> "Image.Image":
        """Renders a component label to a 1-bit PIL Image using system fonts.

        Layout:
          - Part number:  bold, ~2× normal font size
          - Separator line
          - Description:  bold weight, word-wrapped

        The image width is fixed to *dot_width* pixels (printer paper width).
        """
        if Image is None:
            raise RuntimeError("Pillow is required for bitmap label printing.")

        MARGIN = 6
        usable_w = dot_width - 2 * MARGIN

        def _load_font(paths, size):
            for p in paths:
                try:
                    return ImageFont.truetype(p, size)
                except (IOError, OSError):
                    pass
            return ImageFont.load_default()

        font_pn = _load_font(FONT_PATHS_BOLD, 38)     # large part-number (bold)
        font_desc = _load_font(FONT_PATHS_NORMAL, 22) # normal description (clean & readable)

        # --- Measure and word-wrap description ---
        dummy = Image.new('1', (1, 1))
        draw_dummy = ImageDraw.Draw(dummy)

        def _wrap(text, font, max_w):
            words = text.split()
            lines, current = [], []
            for word in words:
                trial = ' '.join(current + [word])
                bbox = draw_dummy.textbbox((0, 0), trial, font=font)
                if bbox[2] - bbox[0] > max_w and current:
                    lines.append(' '.join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                lines.append(' '.join(current))
            return lines

        desc_lines = _wrap(description, font_desc, usable_w)

        def _measure_text_h(text: str, font) -> int:
            bbox = draw_dummy.textbbox((0, 0), text, font=font)
            return bbox[3] - bbox[1]

        pn_h = _measure_text_h(part_number, font_pn)
        line_h = _measure_text_h("Ag", font_desc) + 6
        sep_gap = 6

        total_h = (MARGIN
                   + pn_h
                   + sep_gap + 2 + sep_gap
                   + line_h * len(desc_lines)
                   + MARGIN)

        # Render on a grayscale canvas first so TrueType anti-aliasing can render smoothly,
        # then threshold at 190. Drawing directly on mode '1' causes Pillow to apply a hard 128
        # cutoff that hollows out regular fonts into thin, faint 1-pixel skeletons.
        img_gray = Image.new('L', (dot_width, total_h), 255)  # white background
        draw = ImageDraw.Draw(img_gray)

        y = MARGIN
        draw.text((MARGIN, y), part_number, font=font_pn, fill=0)
        y += pn_h + sep_gap

        draw.line([(MARGIN, y), (dot_width - MARGIN, y)], fill=0, width=2)
        y += 2 + sep_gap

        for line in desc_lines:
            draw.text((MARGIN, y), line, font=font_desc, fill=0)
            y += line_h

        # Convert to 1-bit: any pixel with >=25% ink (gray < 190) becomes solid black
        img_1bit = img_gray.point(lambda p: 0 if p < 190 else 255, mode='1')
        return img_1bit

    def render_catalog_label_image(
        self,
        comp_type: str,
        part_number: str,
        brief_desc: str,
        category: str,
        decimal_pn: str,
        location: str,
        price: str,
        description: str,
        mfr_part_number: Optional[str] = None,
        date_updated: Optional[str] = None,
        dot_width: int = PRINTER_DOTS_PER_LINE,
    ) -> Image.Image:
        """Renders the catalog label as a 1-bit monochrome PIL Image.

        Uses TrueType font rendering, anti-aliased scaling, and layout matching label_format.md.
        """
        MARGIN = 12
        usable_w = dot_width - (MARGIN * 2)

        def _load_font(paths, size):
            for p in paths:
                try:
                    return ImageFont.truetype(p, size)
                except (IOError, OSError):
                    pass
            return ImageFont.load_default()

        font_type = _load_font(FONT_PATHS_BOLD, 28)      # Component type (BOB) in black badge
        font_pn = _load_font(FONT_PATHS_BOLD, 30)        # Part number (large bold)
        font_sub = _load_font(FONT_PATHS_NORMAL, 18)     # Mfr part number (Adafruit 2264)
        font_brief = _load_font(FONT_PATHS_BOLD, 20)     # Brief description (bold, up to 2 lines)
        font_meta = _load_font(FONT_PATHS_NORMAL, 17)    # Category, Dec PN, Location, Date
        font_price = _load_font(FONT_PATHS_BOLD, 20)     # Price (bold)
        font_body = _load_font(FONT_PATHS_NORMAL, 17)    # 100-word body description (clean, non-bold)

        dummy = Image.new('1', (1, 1))
        draw_dummy = ImageDraw.Draw(dummy)

        def _wrap(text, font, max_w):
            words = text.split()
            lines, current = [], []
            for word in words:
                trial = ' '.join(current + [word])
                bbox = draw_dummy.textbbox((0, 0), trial, font=font)
                if bbox[2] - bbox[0] > max_w and current:
                    lines.append(' '.join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                lines.append(' '.join(current))
            return lines

        def _text_bbox(text, font):
            return draw_dummy.textbbox((0, 0), text, font=font)

        # Date formatting
        if not date_updated:
            from datetime import datetime
            date_updated = datetime.now().strftime("%Y-%m-%d")
        date_display = date_updated if date_updated.startswith("Last updated:") else f"Last updated: {date_updated}"

        brief_lines = _wrap(brief_desc, font_brief, usable_w)
        cat_lines = _wrap(category, font_meta, usable_w)
        price_lines = _wrap(price, font_price, usable_w)
        body_lines = _wrap(description, font_body, usable_w)

        h_brief_line = 25
        h_meta_line = 23
        h_body_line = 23

        type_bbox = _text_bbox(comp_type, font_type)
        badge_w = (type_bbox[2] - type_bbox[0]) + 14
        badge_h = (type_bbox[3] - type_bbox[1]) + 8

        pn_bbox = _text_bbox(part_number, font_pn)
        line1_h = max(badge_h, pn_bbox[3] - pn_bbox[1])

        total_h = MARGIN + line1_h + 8
        if mfr_part_number:
            total_h += h_meta_line + 4
        total_h += len(brief_lines) * h_brief_line + 6
        total_h += 12                # Divider 1 after brief description
        total_h += len(cat_lines) * h_meta_line + 4
        if decimal_pn:
            total_h += h_meta_line + 4  # decimal PN
        if location:
            total_h += h_meta_line + 4  # location
        if price:
            total_h += len(price_lines) * h_brief_line + 6  # price
        total_h += h_meta_line + 6  # Line 7: Last updated date
        total_h += 12                # Divider 2 before description
        total_h += len(body_lines) * h_body_line + MARGIN

        img_gray = Image.new('L', (dot_width, total_h), 255)
        draw = ImageDraw.Draw(img_gray)

        y = MARGIN

        # Line 1: [ BOB ] FT232H
        draw.rounded_rectangle([MARGIN, y, MARGIN + badge_w, y + badge_h], radius=3, fill=0)
        draw.text((MARGIN + 7, y + 2), comp_type, font=font_type, fill=255)
        draw.text((MARGIN + badge_w + 10, y), part_number, font=font_pn, fill=0)
        y += line1_h + 8

        # Line 1.5: Manufacturer part number
        if mfr_part_number:
            draw.text((MARGIN, y), mfr_part_number, font=font_sub, fill=0)
            y += h_meta_line + 4

        # Line 2: Brief description (Bold)
        for line in brief_lines:
            draw.text((MARGIN, y), line, font=font_brief, fill=0)
            y += h_brief_line
        y += 4

        # Divider line 1 (after brief description)
        draw.line([(MARGIN, y), (dot_width - MARGIN, y)], fill=0, width=2)
        y += 6

        # Line 3: Category
        for line in cat_lines:
            draw.text((MARGIN, y), line, font=font_meta, fill=0)
            y += h_meta_line
        y += 4

        # Line 4: Database decimal ID
        if decimal_pn:
            db_id_text = decimal_pn if decimal_pn.startswith("Database ID:") else f"Database ID: {decimal_pn}"
            draw.text((MARGIN, y), db_id_text, font=font_meta, fill=0)
            y += h_meta_line + 4

        # Line 5: Location
        if location:
            draw.text((MARGIN, y), location, font=font_meta, fill=0)
            y += h_meta_line + 4

        # Line 6: Price (Bold)
        if price:
            for line in price_lines:
                draw.text((MARGIN, y), line, font=font_price, fill=0)
                y += h_brief_line
            y += 4
        y += 4

        # Line 7: Date printed
        draw.text((MARGIN, y), date_display, font=font_meta, fill=0)
        y += h_meta_line + 4

        # Divider line 2 (before description)
        draw.line([(MARGIN, y), (dot_width - MARGIN, y)], fill=0, width=2)
        y += 8

        # Line 8: Description
        for line in body_lines:
            draw.text((MARGIN, y), line, font=font_body, fill=0)
            y += h_body_line

        return img_gray.point(lambda p: 0 if p < 190 else 255, mode='1')

    # --- TEXT EFFECTS ---
    def set_bold(self, enabled: bool = True) -> None:
        """Turns Bold on or off (ESC E n)."""
        if self.ser:
            val = b'\x01' if enabled else b'\x00'
            self._wait_for_ready()
            self.ser.write(b'\x1b\x45' + val)

    def set_underline(self, enabled: bool = True) -> None:
        """Turns Underline on or off (ESC - n)."""
        if self.ser:
            val = b'\x01' if enabled else b'\x00'
            self._wait_for_ready()
            self.ser.write(b'\x1b\x2d' + val)

    def set_invert(self, enabled: bool = True) -> None:
        """Turns White-on-Black inverse text mode on or off (GS B n)."""
        if self.ser:
            val = b'\x01' if enabled else b'\x00'
            self._wait_for_ready()
            self.ser.write(b'\x1d\x42' + val)

    # --- JUSTIFICATION ---
    def set_justification(self, align: str = 'left') -> None:
        """Aligns text: 'left', 'center', or 'right' (ESC a n)."""
        if self.ser:
            align = align.lower()
            if align == 'left':
                self._wait_for_ready()
                self.ser.write(b'\x1b\x61\x00')
            elif align == 'center':
                self._wait_for_ready()
                self.ser.write(b'\x1b\x61\x01')
            elif align == 'right':
                self._wait_for_ready()
                self.ser.write(b'\x1b\x61\x02')

    # --- TEXT SIZING ---
    def set_size(self, size: str = 'normal') -> None:
        """Sets character sizing using standard GS ! formatting options."""
        if self.ser:
            size = size.lower()
            self._wait_for_ready()
            if size == 'normal':
                self.ser.write(b'\x1d\x21\x00')  # Normal 1x Width, 1x Height
            elif size == 'double_height':
                self.ser.write(b'\x1d\x21\x01')  # 1x Width, 2x Height
            elif size == 'double_width':
                self.ser.write(b'\x1d\x21\x10')  # 2x Width, 1x Height
            elif size == 'large':
                self.ser.write(b'\x1d\x21\x11')  # 2x Width, 2x Height

    # --- BARCODES ---
    def print_barcode(self, data: str, system: str = 'UPC-A') -> None:
        """Prints a barcode based on legacy firmware rules (GS k m data NUL)."""
        if not self.ser:
            logger.info("[PRINTER MOCK BARCODE (%s)] %s", system, data)
            return

        systems = {
            'UPC-A': b'\x00',
            'UPC-E': b'\x01',
            'EAN13': b'\x02',
            'EAN8':  b'\x03',
            'CODE39': b'\x04',
        }
        system_key = system.upper()
        if system_key not in systems:
            raise ValueError(f"Unsupported legacy barcode system: {system_key}")

        cmd = b'\x1d\x6b' + systems[system_key] + data.encode('ascii') + b'\x00'
        self._wait_for_ready()
        self.ser.write(cmd)
        time.sleep(0.1)

    # --- HIGH LEVEL LABEL PRINTING ---
    def print_component_label(
        self,
        part_number: str,
        description: str,
        mode: str = 'text',
    ) -> None:
        """Prints an electronic component label.

        By default, uses native ESC/POS text mode ('text'). This uses the printer's
        internal character ROM and sends ~150 bytes total, completely eliminating the
        serial FIFO buffer overruns that cause random CP437 character explosions
        (█ █ █, Greek symbols, ddd000000ppp) in bitmap mode.

        Layout (text mode):
          - Part number:  Large 2×, Bold, Left-aligned
          - Separator:    Single dashed divider line
          - Description:  Normal size, non-bold, wrapped to 32 characters
        """
        logger.info("Printing component label (%s): %s", mode, part_number)

        if mode == 'bitmap':
            self.feed(1)
            label_img = self.render_label_image(part_number, description)
            self.print_bitmap(label_img)
            self.feed(3)
            return

        # --- Native ESC/POS Text Mode (buffer-safe, fast) ---
        self.feed(1)

        # Part Number (Large 2× Width/Height, Bold)
        self.set_justification('left')
        time.sleep(0.02)
        self.set_bold(True)
        time.sleep(0.02)
        self.set_size('large')
        time.sleep(0.02)
        self.write_line(part_number)

        # Reset to normal size and weight for the divider and description
        self.set_size('normal')
        time.sleep(0.02)
        self.set_bold(False)
        time.sleep(0.02)
        self.write_line("-" * PRINTER_CHARS_PER_LINE)

        # Description (Normal size, non-bold, word-wrapped to paper width)
        wrapped_lines = textwrap.wrap(description, width=PRINTER_CHARS_PER_LINE)
        for line in wrapped_lines:
            self.write_line(line)

        # Clean feed for tearing
        self.feed(3)

    def print_catalog_label(
        self,
        comp_type: str,
        part_number: str,
        brief_desc: str,
        category: str,
        decimal_pn: str,
        location: str,
        price: str,
        description: str,
        mfr_part_number: Optional[str] = None,
        date_updated: Optional[str] = None,
        mode: str = PRINTER_LABEL_MODE,
    ) -> None:
        """Prints a component catalog label conforming to label_format.md.

        Supports both 'text' (native ESC/POS) and 'bitmap' (Pillow TrueType rendering).
        """
        logger.info("Printing catalog label (%s): [%s] %s", mode, comp_type, part_number)
        if not self.use_default_settings:
            self.set_heat_config()

        if mode == 'bitmap':
            self.feed(1)
            img = self.render_catalog_label_image(
                comp_type=comp_type,
                part_number=part_number,
                brief_desc=brief_desc,
                category=category,
                decimal_pn=decimal_pn,
                location=location,
                price=price,
                description=description,
                mfr_part_number=mfr_part_number,
                date_updated=date_updated,
            )
            self.print_bitmap(img)
            self.feed(3)
            return

        # --- Native ESC/POS Text Mode ---
        self.feed(1)

        # Line 1: [ BOB ] FT232H (Double size, bold inverse badge + double size part number)
        self.set_justification('left')
        self.set_size('large')
        self.set_bold(True)
        self.set_invert(True)
        self.write(f" {comp_type} ")
        self.set_invert(False)
        self.set_bold(False)
        self.write_line(f" {part_number}")

        # Line 1.5: Manufacturer part number (if present)
        self.set_size('normal')
        self.set_bold(False)
        if mfr_part_number:
            self.write_line(mfr_part_number)

        # Line 2: Brief description (Bold, max 64 chars / 2 lines)
        self.set_bold(True)
        for line in textwrap.wrap(brief_desc, width=PRINTER_CHARS_PER_LINE):
            self.write_line(line)
        self.set_bold(False)

        # Divider line 1 (after brief description)
        self.write_line("-" * PRINTER_CHARS_PER_LINE)

        # Line 3: Category (Normal)
        for line in textwrap.wrap(category, width=PRINTER_CHARS_PER_LINE):
            self.write_line(line)

        # Line 4: Database decimal ID
        if decimal_pn:
            db_id_text = decimal_pn if decimal_pn.startswith("Database ID:") else f"Database ID: {decimal_pn}"
            self.write_line(db_id_text)

        # Line 5: Location
        if location:
            self.write_line(location)

        # Line 6: Price (Bold)
        if price:
            self.set_bold(True)
            for line in textwrap.wrap(price, width=PRINTER_CHARS_PER_LINE):
                self.write_line(line)
            self.set_bold(False)

        # Line 7: Date printed
        if not date_updated:
            from datetime import datetime
            date_updated = datetime.now().strftime("%Y-%m-%d")
        date_display = date_updated if date_updated.startswith("Last updated:") else f"Last updated: {date_updated}"
        self.write_line(date_display)

        # Divider line 2 (before description)
        self.write_line("-" * PRINTER_CHARS_PER_LINE)

        # Line 8: 100-word Description (Normal)
        for line in textwrap.wrap(description, width=PRINTER_CHARS_PER_LINE):
            self.write_line(line)

        # Clean feed for tearing
        self.feed(3)

    def close(self) -> None:
        """Flushes pending writes, waits for mechanical completion, and closes cleanly."""
        if self.ser:
            try:
                self.ser.flush()
                # Crucial: let stepper motor finish physical paper feed before dropping UART
                time.sleep(0.25)
                self.ser.close()
            except Exception:
                pass
            self.ser = None


ThermalPrinter = LegacyThermalPrinter

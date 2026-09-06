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
    PRINTER_PORT,
)

logger = logging.getLogger(__name__)


class LegacyThermalPrinter:
    """Lightweight driver for legacy Adafruit/ESC-POS thermal printers (v2.16.x)."""

    def __init__(self, port: str = PRINTER_PORT, baudrate: int = PRINTER_BAUDRATE, timeout: float = 1.0,
                 dtr_pin: Optional[int] = PRINTER_DTR_PIN):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.dtr_pin = dtr_pin
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

    def _send_buffered(self, data: bytes, chunk_size: int = 32) -> None:
        """Sends data in small chunks, polling DTR flow control before each chunk.

        Micro thermal printer receive FIFOs are only 64-128 bytes. Sending a large
        packet (e.g. 1,158 bytes) in a single write overruns the printer's FIFO,
        dropping bytes and causing subsequent raw binary bitmap data to be
        misinterpreted as random garbled ASCII characters.
        """
        if not self.ser:
            return
        has_dtr = (self.dtr_pin is not None and GPIO is not None)
        for i in range(0, len(data), chunk_size):
            if has_dtr:
                self._wait_for_ready()
            else:
                time.sleep(chunk_size * 10.0 / self.baudrate)
            self.ser.write(data[i:i + chunk_size])
        self.ser.flush()

    def _connect(self) -> None:
        if serial is None:
            logger.warning("pyserial is not installed. Running in mock printer mode.")
            return

        try:
            self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
            time.sleep(0.5)
            self.reset()
            logger.info("Thermal printer connected on %s at %d baud.", self.port, self.baudrate)
        except Exception as err:
            logger.warning("Could not open thermal printer on %s: %s (mock mode active)", self.port, err)
            self.ser = None

    def reset(self) -> None:
        """Resets printer memory settings to defaults and applies dark print parameters."""
        if self.ser:
            self._wait_for_ready()
            self.ser.write(b'\x1b\x40')
            time.sleep(0.1)
            # Enable DTR/ASB flow control on printer if DTR pin is configured
            if self.dtr_pin is not None:
                self.ser.write(b'\x1d\x61\x20')  # GS a 32 (enable ASB / DTR)
        # Apply dark heating parameters immediately after reset
        self.set_heat_config()
        self.set_print_density()

    def set_heat_config(
        self,
        dots: int = PRINTER_HEAT_DOTS,
        heat_time: int = PRINTER_HEAT_TIME,
        interval: int = PRINTER_HEAT_INTERVAL,
    ) -> None:
        """Sets heating control parameters (ESC 7 n1 n2 n3).
        dots: Max heating dots fired simultaneously (0-255, in units of 8 dots).
        heat_time: Heating duration per dot (3-255, in units of 10µs). Higher = darker.
        interval: Recovery cooling interval between dot groups (0-255, in units of 10µs).
        """
        if self.ser:
            cmd = b'\x1b\x37' + bytes([dots & 0xFF, heat_time & 0xFF, interval & 0xFF])
            self._wait_for_ready()
            self.ser.write(cmd)
            time.sleep(0.05)
        else:
            logger.info("[PRINTER MOCK] set_heat_config(dots=%d, time=%d, interval=%d)", dots, heat_time, interval)

    def set_print_density(
        self,
        density: int = PRINTER_DENSITY,
        break_time: int = PRINTER_BREAK_TIME,
    ) -> None:
        """Sets print darkness density and break time (DC2 # n).
        density: 0-31 (0 = 50%, 10 = 100%, 31 = 205% max darkness).
        break_time: 0-7 (in units of 250µs).
        """
        if self.ser:
            val = ((break_time & 0x07) << 5) | (density & 0x1F)
            cmd = b'\x12\x23' + bytes([val])
            self._wait_for_ready()
            self.ser.write(cmd)
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

    def write_line(self, text: str) -> None:
        """Prints a string line encoded in ASCII/CP437 layout."""
        if self.ser:
            self._wait_for_ready()
            self.ser.write(text.encode('ascii', errors='ignore') + b'\n')
        else:
            logger.info("[PRINTER MOCK] %s", text)

    def feed(self, lines: int = 1) -> None:
        """Feeds the paper by a specified number of lines."""
        if self.ser:
            for _ in range(lines):
                self._wait_for_ready()
                self.ser.write(b'\n')
        else:
            logger.info("[PRINTER MOCK FEED %d lines]", lines)

    # --- BITMAP / RASTER PRINTING ---

    def print_bitmap(self, image: "Image.Image") -> None:
        """Sends a PIL image using ESC * 24-dot double-density column mode.

        GS v 0 (raster mode) is unreliable on v2.16 firmware. ESC * (column
        bit-image mode) is the legacy-safe method used by the Adafruit library.

        The image is processed in 24-row strips. For each strip, the column
        data is packed MSB-first (topmost dot = bit 7) and sent as:
            ESC * 33 nL nH  [3 bytes per column × width]
        with line spacing set to exactly 24 dots between strips.
        """
        if Image is None:
            logger.warning("Pillow not installed — cannot print bitmap.")
            return

        bw = image.convert('1')
        w, h = bw.size
        pixels = bw.load()

        if not self.ser:
            logger.info("[PRINTER MOCK BITMAP] %dx%d px", w, h)
            return

        # Ensure dark heat & density settings are active before printing
        self.set_heat_config()
        self.set_print_density()

        # Set line spacing to 24 dots so strips tile flush
        self._wait_for_ready()
        self.ser.write(b'\x1b\x33\x18')  # ESC 3 24
        self.ser.flush()

        for y0 in range(0, h, 24):
            strip_h = min(24, h - y0)

            # Build column data: 3 bytes per column (24 vertical dots each)
            col_data = bytearray()
            for x in range(w):
                b0 = b1 = b2 = 0
                for row in range(strip_h):
                    y = y0 + row
                    # PIL '1': 0 = black (print dot), 255 = white
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
            self._send_buffered(strip_packet, chunk_size=32)

        # Restore default line spacing (1/6 inch)
        self._wait_for_ready()
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
    def print_component_label(self, part_number: str, description: str) -> None:
        """Prints an electronic component label as a pre-rendered bitmap.

        Text is rasterised with Pillow into a 1-bit image and sent to the printer
        via the ESC/POS GS v 0 raster command.  This avoids all ESC/POS text-mode
        artefacts (streaks, fading) caused by per-character heat cycling.
        """
        logger.info("Printing component label (bitmap): %s", part_number)

        # Enforce dark heating and density settings
        self.set_heat_config()
        self.set_print_density()

        self.feed(1)

        label_img = self.render_label_image(part_number, description)
        self.print_bitmap(label_img)

        # Clean feed for tearing
        self.feed(3)

    def close(self) -> None:
        """Closes the serial connection and releases GPIO resources safely."""
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        if self.dtr_pin is not None and GPIO is not None:
            try:
                GPIO.cleanup(self.dtr_pin)
            except Exception:
                pass

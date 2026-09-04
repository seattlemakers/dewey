"""Thermal printer driver for Dewey legacy ESC/POS printer (v2.16 firmware)."""

import logging
import textwrap
import time
from typing import Optional

try:
    import serial
except ImportError:
    serial = None

from dewey.config import PRINTER_BAUDRATE, PRINTER_CHARS_PER_LINE, PRINTER_PORT

logger = logging.getLogger(__name__)


class LegacyThermalPrinter:
    """Lightweight driver for legacy Adafruit/ESC-POS thermal printers (v2.16.x)."""

    def __init__(self, port: str = PRINTER_PORT, baudrate: int = PRINTER_BAUDRATE, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional["serial.Serial"] = None
        self._connect()

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
        """Resets printer memory settings to defaults."""
        if self.ser:
            self.ser.write(b'\x1b\x40')
            time.sleep(0.1)

    def write_line(self, text: str) -> None:
        """Prints a string line encoded in ASCII/CP437 layout."""
        if self.ser:
            self.ser.write(text.encode('ascii', errors='ignore') + b'\n')
        else:
            logger.info("[PRINTER MOCK] %s", text)

    def feed(self, lines: int = 1) -> None:
        """Feeds the paper by a specified number of lines."""
        if self.ser:
            for _ in range(lines):
                self.ser.write(b'\n')
        else:
            logger.info("[PRINTER MOCK FEED %d lines]", lines)

    # --- TEXT EFFECTS ---
    def set_bold(self, enabled: bool = True) -> None:
        """Turns Bold on or off (ESC E n)."""
        if self.ser:
            val = b'\x01' if enabled else b'\x00'
            self.ser.write(b'\x1b\x45' + val)

    def set_underline(self, enabled: bool = True) -> None:
        """Turns Underline on or off (ESC - n)."""
        if self.ser:
            val = b'\x01' if enabled else b'\x00'
            self.ser.write(b'\x1b\x2d' + val)

    def set_invert(self, enabled: bool = True) -> None:
        """Turns White-on-Black inverse text mode on or off (GS B n)."""
        if self.ser:
            val = b'\x01' if enabled else b'\x00'
            self.ser.write(b'\x1d\x42' + val)

    # --- JUSTIFICATION ---
    def set_justification(self, align: str = 'left') -> None:
        """Aligns text: 'left', 'center', or 'right' (ESC a n)."""
        if self.ser:
            align = align.lower()
            if align == 'left':
                self.ser.write(b'\x1b\x61\x00')
            elif align == 'center':
                self.ser.write(b'\x1b\x61\x01')
            elif align == 'right':
                self.ser.write(b'\x1b\x61\x02')

    # --- TEXT SIZING ---
    def set_size(self, size: str = 'normal') -> None:
        """Sets character sizing using standard GS ! formatting options."""
        if self.ser:
            size = size.lower()
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
        self.ser.write(cmd)
        time.sleep(0.1)

    # --- HIGH LEVEL LABEL PRINTING ---
    def print_component_label(self, part_number: str, description: str) -> None:
        """Prints an electronic component label:
        - Part number in large text at top
        - Description in small/normal text below
        """
        logger.info("Printing component label: %s", part_number)
        self.feed(1)

        # Part Number (Large, Centered or Left, Bold)
        self.set_justification('left')
        self.set_bold(True)
        self.set_size('large')
        self.write_line(part_number)

        # Reset formatting
        self.set_size('normal')
        self.set_bold(False)
        self.feed(1)

        # Description (Normal / Small, Left-aligned, wrapped to 32 chars)
        wrapped_lines = textwrap.wrap(description, width=PRINTER_CHARS_PER_LINE)
        for line in wrapped_lines:
            self.write_line(line)

        # Clean feed for tearing
        self.feed(3)

    def close(self) -> None:
        """Closes the serial connection safely."""
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

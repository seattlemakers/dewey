"""Thermal printer driver for Dewey legacy ESC/POS printer (v2.16 firmware)."""

import logging
import textwrap
import time
from typing import Optional

try:
    import serial
except ImportError:
    serial = None

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from dewey.config import (
    PRINTER_BAUDRATE,
    PRINTER_BREAK_TIME,
    PRINTER_CHARS_PER_LINE,
    PRINTER_DENSITY,
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
        """Prints a string line encoded in ASCII/CP437 layout.

        A short sleep is added after each write so the printer fully heats and
        resets between lines, preventing faded/streaky output from buffer pressure.
        """
        if self.ser:
            self._wait_for_ready()
            self.ser.write(text.encode('ascii', errors='ignore') + b'\n')
            time.sleep(0.05)
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
        """Prints an electronic component label:
        - Part number in large text at top
        - Description in small/normal text below
        Enforces maximum print density, heat time, bold, and double-strike for deep dark prints.
        """
        logger.info("Printing component label: %s (dark mode)", part_number)

        # Enforce dark heating and density settings
        self.set_heat_config()
        self.set_print_density()
        self.set_double_strike(True)

        self.feed(1)

        # Part Number (Large, Left, Bold, Double Strike)
        self.set_justification('left')
        self.set_bold(True)
        self.set_size('large')
        self.write_line(part_number)

        # Reset size for description, but keep bold + double strike for darkness
        self.set_size('normal')
        self.set_bold(True)
        self.feed(1)

        # Description (Normal / Small, Left-aligned, wrapped to 32 chars)
        wrapped_lines = textwrap.wrap(description, width=PRINTER_CHARS_PER_LINE)
        for line in wrapped_lines:
            self.write_line(line)

        # Reset text styling
        self.set_bold(False)
        self.set_double_strike(False)

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

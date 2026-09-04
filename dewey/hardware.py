"""Hardware interface for switches (Scan, Print) and 4x4 matrix keypad."""

import logging
import time
from typing import List, Optional

try:
    from gpiozero import Button, DigitalInputDevice, DigitalOutputDevice
except ImportError:
    Button = None
    DigitalInputDevice = None
    DigitalOutputDevice = None

from dewey.config import (
    KEYPAD_COLS,
    KEYPAD_MAP,
    KEYPAD_ROWS,
    PIN_PRINT_SWITCH,
    PIN_SCAN_SWITCH,
)

logger = logging.getLogger(__name__)


class Keypad4x4:
    """Matrix scanner for 4x4 keypad with software debouncing."""

    def __init__(self, row_pins: List[int] = KEYPAD_ROWS, col_pins: List[int] = KEYPAD_COLS):
        self.row_pins = row_pins
        self.col_pins = col_pins
        self.keymap = KEYPAD_MAP
        self.last_key_pressed: Optional[str] = None
        self.rows: List[DigitalInputDevice] = []
        self.cols: List[DigitalOutputDevice] = []

        if DigitalInputDevice is not None and DigitalOutputDevice is not None:
            try:
                self.rows = [DigitalInputDevice(pin, pull_up=True) for pin in self.row_pins]
                self.cols = [DigitalOutputDevice(pin, active_high=True, initial_value=True) for pin in self.col_pins]
                logger.info("Keypad initialized on rows=%s, cols=%s", self.row_pins, self.col_pins)
            except Exception as err:
                logger.warning("Could not initialize keypad GPIOs: %s (mock keypad mode)", err)
                self.rows = []
                self.cols = []

    def scan_matrix(self) -> Optional[str]:
        """Low-level scan. Returns key string currently closed, or None."""
        if not self.rows or not self.cols:
            return None

        for col_idx, col_device in enumerate(self.cols):
            col_device.off()  # Drive column LOW (0V)
            time.sleep(0.001)  # Stabilization buffer

            for row_idx, row_device in enumerate(self.rows):
                if row_device.is_active:  # Active when physically pulled LOW
                    col_device.on()
                    return self.keymap[row_idx][col_idx]

            col_device.on()  # Revert column to HIGH (3.3V)
        return None

    def read_key(self) -> Optional[str]:
        """Returns a key name only on initial press event with debouncing."""
        current_key = self.scan_matrix()

        if current_key is None:
            self.last_key_pressed = None
            return None

        if current_key == self.last_key_pressed:
            return None

        time.sleep(0.02)  # Debounce delay
        confirm_key = self.scan_matrix()
        if confirm_key == current_key:
            self.last_key_pressed = current_key
            logger.debug("Keypad press detected: %s", current_key)
            return current_key

        return None

    def close(self) -> None:
        """Closes all GPIO devices."""
        for r in self.rows:
            try:
                r.close()
            except Exception:
                pass
        for c in self.cols:
            try:
                c.close()
            except Exception:
                pass
        self.rows.clear()
        self.cols.clear()


class HardwareManager:
    """Manages switches and keypad events for Dewey."""

    def __init__(self):
        self.btn_scan: Optional[Button] = None
        self.btn_print: Optional[Button] = None
        self.keypad = Keypad4x4()

        self._prev_scan_state = False
        self._prev_print_state = False

        self._init_buttons()

    def _init_buttons(self) -> None:
        if Button is None:
            logger.warning("gpiozero is not installed. Running in mock hardware mode.")
            return

        try:
            # Buttons connect to GND; pull_up=True detects press when pin goes LOW
            self.btn_scan = Button(PIN_SCAN_SWITCH, pull_up=True, bounce_time=0.05)
            self.btn_print = Button(PIN_PRINT_SWITCH, pull_up=True, bounce_time=0.05)
            logger.info("Buttons initialized: Scan on GPIO %d, Print on GPIO %d", PIN_SCAN_SWITCH, PIN_PRINT_SWITCH)
        except Exception as err:
            logger.warning("Failed to initialize buttons: %s (mock buttons mode)", err)
            self.btn_scan = None
            self.btn_print = None

    def is_scan_pressed(self) -> bool:
        """Returns True if Scan button was pressed since last check."""
        if not self.btn_scan:
            return False

        current = self.btn_scan.is_pressed
        pressed = current and not self._prev_scan_state
        self._prev_scan_state = current
        return pressed

    def is_print_pressed(self) -> bool:
        """Returns True if Print button was pressed since last check."""
        if not self.btn_print:
            return False

        current = self.btn_print.is_pressed
        pressed = current and not self._prev_print_state
        self._prev_print_state = current
        return pressed

    def read_keypad(self) -> Optional[str]:
        """Polls keypad and returns pressed key if any."""
        return self.keypad.read_key()

    def is_f4_pressed(self) -> bool:
        """Checks if F4 was pressed on the keypad."""
        key = self.read_keypad()
        return key == "F4"

    def close(self) -> None:
        """Cleans up all GPIO lines."""
        if self.btn_scan:
            try:
                self.btn_scan.close()
            except Exception:
                pass
        if self.btn_print:
            try:
                self.btn_print.close()
            except Exception:
                pass
        self.keypad.close()
        logger.info("Hardware devices closed cleanly.")

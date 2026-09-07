"""Non-blocking keyboard input manager supporting USB keyboards and terminal sessions."""

import logging
import os
import select
import sys
import termios
import threading
import time
import tty
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None
    ecodes = None


class KeyboardManager:
    """Listens for keyboard input non-blockingly from stdin and direct Linux USB HID devices."""

    def __init__(self):
        self.old_termios = None
        self.is_tty = False
        self._init_terminal()

        # Buffer for events read from direct evdev USB keyboards
        self._evdev_queue = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._evdev_thread = None

        if evdev is not None:
            self._start_evdev_listener()

    def _init_terminal(self) -> None:
        """Sets terminal to cbreak mode so keys are read immediately without waiting for enter."""
        try:
            if sys.stdin.isatty():
                self.is_tty = True
                self.old_termios = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
                logger.info("Terminal cbreak mode initialized for USB/terminal keyboard.")
        except Exception as err:
            logger.debug("Could not initialize cbreak on stdin: %s", err)
            self.is_tty = False

    def _start_evdev_listener(self) -> None:
        """Finds USB keyboard devices under /dev/input and starts reader thread."""
        try:
            device_paths = evdev.list_devices()
            devices = []
            for p in device_paths:
                try:
                    d = evdev.InputDevice(p)
                    caps = d.capabilities()
                    if ecodes.EV_KEY in caps and ("keyboard" in d.name.lower() or "kbd" in d.name.lower()):
                        devices.append(d)
                except Exception:
                    pass

            if devices:
                self._evdev_thread = threading.Thread(
                    target=self._evdev_loop,
                    args=(devices,),
                    daemon=True,
                    name="DeweyEvdevKbd",
                )
                self._evdev_thread.start()
                logger.info("Direct USB keyboard listener active for: %s", [d.name for d in devices])
        except Exception as err:
            logger.debug("evdev keyboard detection skipped: %s", err)

    def _evdev_loop(self, devices) -> None:
        """Polls evdev devices for keypresses in background thread."""
        import selectors
        sel = selectors.DefaultSelector()
        for d in devices:
            sel.register(d, selectors.EVENT_READ)

        shift_pressed = False

        while not self._stop_event.is_set():
            events = sel.select(timeout=0.1)
            for key, _ in events:
                device = key.fileobj
                try:
                    for ev in device.read():
                        if ev.type == ecodes.EV_KEY:
                            # Track shift state
                            if ev.code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                                shift_pressed = (ev.value != 0)
                                continue

                            # Only trigger on key down (1) or hold (2)
                            if ev.value in (1, 2):
                                k_str = self._map_evdev_key(ev.code, shift_pressed)
                                if k_str:
                                    with self._lock:
                                        self._evdev_queue.append(k_str)
                except Exception:
                    pass

    def _map_evdev_key(self, code: int, shift: bool) -> Optional[str]:
        """Maps an evdev keycode to a standard key string."""
        if code == ecodes.KEY_UP:
            return "UP"
        if code == ecodes.KEY_DOWN:
            return "DOWN"
        if code == ecodes.KEY_LEFT:
            return "LEFT"
        if code == ecodes.KEY_RIGHT:
            return "RIGHT"
        if code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER):
            return "ENT"
        if code == ecodes.KEY_ESC:
            return "ESC"
        if code == ecodes.KEY_BACKSPACE:
            return "BACKSPACE"
        if code == ecodes.KEY_TAB:
            return "TAB"
        if code in (ecodes.KEY_DELETE, ecodes.KEY_KPDOT):
            return "." if code == ecodes.KEY_KPDOT else "CLR"

        # Number keys
        num_map = {
            ecodes.KEY_0: "0", ecodes.KEY_1: "1", ecodes.KEY_2: "2", ecodes.KEY_3: "3", ecodes.KEY_4: "4",
            ecodes.KEY_5: "5", ecodes.KEY_6: "6", ecodes.KEY_7: "7", ecodes.KEY_8: "8", ecodes.KEY_9: "9",
            ecodes.KEY_KP0: "0", ecodes.KEY_KP1: "1", ecodes.KEY_KP2: "2", ecodes.KEY_KP3: "3", ecodes.KEY_KP4: "4",
            ecodes.KEY_KP5: "5", ecodes.KEY_KP6: "6", ecodes.KEY_KP7: "7", ecodes.KEY_KP8: "8", ecodes.KEY_KP9: "9",
        }
        if code in num_map:
            return num_map[code]

        if code == ecodes.KEY_DOT:
            return ">" if shift else "."
        if code == ecodes.KEY_SLASH:
            return "?" if shift else "/"
        if code == ecodes.KEY_MINUS:
            return "_" if shift else "-"
        if code == ecodes.KEY_SPACE:
            return " "

        # Alpha keys
        name = ecodes.KEY[code] if code in ecodes.KEY else ""
        if name.startswith("KEY_") and len(name) == 5:
            char = name[4]
            return char.upper() if shift else char.lower()

        return None

    def read_key(self) -> Optional[str]:
        """Non-blockingly reads the next key from either stdin or evdev USB keyboard.
        Returns None if no key was pressed.
        """
        # 1. Check evdev queue first
        with self._lock:
            if self._evdev_queue:
                return self._evdev_queue.pop(0)

        # 2. Check stdin
        if not self.is_tty:
            return None

        try:
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if not r:
                return None

            ch = sys.stdin.read(1)
            if not ch:
                return None

            # Handle ANSI Escape Sequences (Arrow keys, F-keys)
            if ch == "\x1b":
                # Check if there are subsequent escape bytes
                r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not r2:
                    return "ESC"

                seq = sys.stdin.read(1)
                if seq in ("[", "O"):
                    r3, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r3:
                        code = sys.stdin.read(1)
                        if seq == "[":
                            if code == "A":
                                return "UP"
                            if code == "B":
                                return "DOWN"
                            if code == "C":
                                return "RIGHT"
                            if code == "D":
                                return "LEFT"
                            if code == "3":
                                # Consume trailing '~' for Delete
                                select.select([sys.stdin], [], [], 0.02)
                                sys.stdin.read(1)
                                return "CLR"
                        elif seq == "O":
                            if code == "P":
                                return "F1"
                            if code == "Q":
                                return "F2"
                            if code == "R":
                                return "F3"
                            if code == "S":
                                return "F4"
                return "ESC"

            if ch in ("\r", "\n"):
                return "ENT"

            if ch in ("\x7f", "\x08"):
                return "BACKSPACE"

            if ch == "\t":
                return "TAB"

            # Printable ASCII character
            return ch

        except Exception:
            return None

    def close(self) -> None:
        """Restores original terminal settings."""
        self._stop_event.set()
        if self.is_tty and self.old_termios:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_termios)
            except Exception:
                pass
            self.is_tty = False

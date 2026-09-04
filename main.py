#!/usr/bin/env python3
"""Dewey - Electronic Component Organizer & Cataloging System.

Main application entry point orchestrating live camera LCD display,
Gemini-powered component identification, thermal printing, and keypad/switch controls.
"""

import argparse
import logging
import signal
import sys
import time
from enum import Enum, auto

from dewey.camera import CameraManager
from dewey.display import DisplayManager
from dewey.gemini_service import GeminiComponentIdentifier
from dewey.hardware import HardwareManager
from dewey.thermal_printer import LegacyThermalPrinter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dewey")


class SystemState(Enum):
    """Dewey application operational states."""
    IDLE = auto()            # Live camera stream to LCD
    SCANNING = auto()        # Capturing photo & calling Gemini
    DISPLAY_RESULT = auto()  # Showing identified part number and description
    ERROR = auto()           # Displaying error message


class DeweyApp:
    """Main application controller for the Dewey system."""

    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self.running = True
        self.state = SystemState.IDLE

        # Hardware and services
        logger.info("Initializing Dewey components...")
        self.display = DisplayManager()
        self.camera = CameraManager()
        self.printer = LegacyThermalPrinter()
        self.hardware = HardwareManager()
        self.gemini = GeminiComponentIdentifier()

        # Current identified part data
        self.current_part_number = ""
        self.current_description = ""
        self.last_error_message = ""

    def run(self) -> None:
        """Main application loop."""
        logger.info("LABRARIAN MK 1 started. Initializing...")
        self.display.show_status("LABRARIAN MK 1", "Initializing camera view...")
        time.sleep(0.8)

        try:
            while self.running:
                if self.state == SystemState.IDLE:
                    self._handle_idle_state()
                elif self.state == SystemState.SCANNING:
                    self._handle_scanning_state()
                elif self.state == SystemState.DISPLAY_RESULT:
                    self._handle_result_state()
                elif self.state == SystemState.ERROR:
                    self._handle_error_state()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received.")
        finally:
            self.shutdown()

    # --- STATE HANDLERS ---

    def _handle_idle_state(self) -> None:
        """Idle state: streams camera to LCD and listens for Scan button."""
        # Update camera frame on LCD
        frame = self.camera.read_preview_frame()
        if frame is not None:
            self.display.show_camera_frame(frame)
        else:
            # Fallback if camera stream is temporarily unavailable
            time.sleep(0.05)

        # Check for Scan button press (Red switch, Pin 5)
        if self.hardware.is_scan_pressed():
            logger.info("Scan button pressed. Transitioning to SCANNING.")
            self.state = SystemState.SCANNING

    def _handle_scanning_state(self) -> None:
        """Scanning state: captures still photo, sends to Gemini, parses response."""
        # Immediately display scanning status on LCD
        self.display.show_status("SCANNING...", "Analyzing with Gemini")

        # Capture high-resolution photograph
        jpeg_bytes = self.camera.capture_high_res_jpeg()
        if not jpeg_bytes:
            logger.error("Failed to capture photograph from camera.")
            self.last_error_message = "Camera capture failed. Please check camera connection."
            self.state = SystemState.ERROR
            return

        # Query Gemini
        try:
            part_number, description = self.gemini.identify_component(jpeg_bytes)
            self.current_part_number = part_number
            self.current_description = description
            logger.info("Analysis complete: %s", part_number)
            self.state = SystemState.DISPLAY_RESULT
        except Exception as err:
            logger.error("Gemini analysis failed: %s", err)
            self.last_error_message = str(err)
            self.state = SystemState.ERROR

    def _handle_result_state(self) -> None:
        """Display Result state: shows part number & description, listens for Print, Rescan, or F4."""
        # Render the result screen
        self.display.show_component_result(self.current_part_number, self.current_description)

        # Wait for user input
        while self.running and self.state == SystemState.DISPLAY_RESULT:
            # 1. Print button pressed (White switch, Pin 6)
            if self.hardware.is_print_pressed():
                logger.info("Print button pressed. Sending label to thermal printer.")
                self.printer.print_component_label(self.current_part_number, self.current_description)

            # 2. Scan button pressed again (Red switch, Pin 5) -> repeat scan
            if self.hardware.is_scan_pressed():
                logger.info("Scan button pressed again. Repeating scan.")
                self.state = SystemState.SCANNING
                break

            # 3. F4 pressed on keypad -> return to idle camera view
            if self.hardware.is_f4_pressed():
                logger.info("F4 pressed on keypad. Returning to IDLE live view.")
                self.state = SystemState.IDLE
                break

            time.sleep(0.03)

    def _handle_error_state(self) -> None:
        """Error state: displays error details, waits for F4 or Rescan."""
        self.display.show_error("ANALYSIS FAILED", self.last_error_message)

        while self.running and self.state == SystemState.ERROR:
            if self.hardware.is_scan_pressed():
                logger.info("Retrying scan from error state.")
                self.state = SystemState.SCANNING
                break

            if self.hardware.is_f4_pressed():
                logger.info("Returning to IDLE from error state.")
                self.state = SystemState.IDLE
                break

            time.sleep(0.03)

    def shutdown(self) -> None:
        """Clean shutdown of all hardware resources."""
        logger.info("Shutting down LABRARIAN MK 1...")
        self.running = False
        try:
            self.display.show_status("LABRARIAN MK 1", "Shutting down...")
            time.sleep(0.3)
        except Exception:
            pass

        self.camera.release()
        self.printer.close()
        self.hardware.close()
        logger.info("Shutdown complete.")


def main():
    parser = argparse.ArgumentParser(description="LABRARIAN MK 1 - Electronic Component System")
    parser.add_argument("--mock", action="store_true", help="Run with simulated hardware")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    app = DeweyApp(mock_mode=args.mock)

    # Signal handlers for clean exit
    def handle_signal(sig, frame):
        logger.info("Received termination signal %d.", sig)
        app.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    app.run()


if __name__ == "__main__":
    main()

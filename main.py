#!/usr/bin/env python3
"""Dewey - Electronic Component Organizer & Cataloging System.

Main application entry point orchestrating live camera LCD display,
Gemini-powered component identification, thermal printing, and keypad/switch controls.
"""

import argparse
import logging
import signal
import subprocess
import sys
import threading
import time
from enum import Enum, auto

from dewey.camera import CameraManager
from dewey.config import (
    COMP_TYPE_OPTIONS,
    LOCATION_OPTIONS,
    PING_HOST,
    PING_INTERVAL,
)
from dewey.display import DisplayManager
from dewey.field_models import (
    LOCATION_TEMPLATES,
    PRICE_TEMPLATES,
    format_location,
    format_price,
    parse_location,
    parse_price,
)
from dewey.gemini_service import GeminiComponentIdentifier
from dewey.hardware import HardwareManager, MultiTapInput
from dewey.keyboard import KeyboardManager
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
        self.keyboard = KeyboardManager()
        self.gemini = GeminiComponentIdentifier()

        # Current identified part data
        self.current_label_data: dict = {}
        self.current_part_number = ""
        self.current_description = ""
        self.last_error_message = ""

        # Network keepalive daemon (pings to prevent SSH / WiFi timeout)
        self.stop_event = threading.Event()
        self.keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            daemon=True,
            name="DeweyKeepalive",
        )
        self.keepalive_thread.start()

    def _keepalive_loop(self) -> None:
        """Background thread periodically pinging to keep WiFi & SSH connection active."""
        logger.info("Network keepalive daemon started (pinging %s every %ds).", PING_HOST, PING_INTERVAL)
        # Perform an initial ping shortly after startup (after 5 seconds)
        if self.stop_event.wait(timeout=5.0):
            return

        initial = True
        while not self.stop_event.is_set():
            try:
                res = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", PING_HOST],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if res.returncode == 0:
                    if initial:
                        logger.info("Keepalive ping to %s verified OK.", PING_HOST)
                        initial = False
                    else:
                        logger.debug("Keepalive ping to %s: OK", PING_HOST)
                else:
                    logger.warning("Keepalive ping to %s: non-zero return code %d", PING_HOST, res.returncode)
            except Exception as err:
                logger.debug("Keepalive ping exception: %s", err)

            if self.stop_event.wait(timeout=PING_INTERVAL):
                break

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

        # Check for Scan button press (Red switch, Pin 5) or keyboard trigger
        kbd_key = self.keyboard.read_key()
        if self.hardware.is_scan_pressed() or kbd_key in ("SCAN", "s", "S", " ", "ENT"):
            logger.info("Scan triggered (switch or keyboard). Transitioning to SCANNING.")
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

        # Query Gemini with vision and web grounding
        try:
            self.current_label_data = self.gemini.identify_component(jpeg_bytes)
            self.current_part_number = self.current_label_data.get("part_number", "UNKNOWN_PART")
            self.current_description = self.current_label_data.get("description", "")
            logger.info("Analysis complete: [%s] %s %s | Price: %s",
                        self.current_label_data.get("comp_type"),
                        self.current_part_number,
                        self.current_label_data.get("mfr_part_number", ""),
                        self.current_label_data.get("price", ""))
            self.state = SystemState.DISPLAY_RESULT
        except Exception as err:
            logger.error("Gemini analysis failed: %s", err)
            self.last_error_message = str(err)
            self.state = SystemState.ERROR

    def _handle_result_state(self) -> None:
        """Display Result & Interactive Label Editor state.

        Controls:
          - Browse mode (is_editing=False):
              F1 / F2 / Up / Down: Move cursor up / down between fields
              ENT / Return: Enter edit mode on selected field
              PRINT switch / 'P': Print label with current edited values
              SCAN switch / 'S' / 'R': Rescan new image
              F4 / ESC / 'Q': Exit to live camera view
          - Edit mode (is_editing=True):
              Option fields (comp_type): F1 / F2 or Up / Down cycles options; CLR resets
              Hierarchical fields (location, price):
                Phase 1: Select template (Beige Cart, Black Cart, South Wall, North Wall, Toolbox / Single, Per Qty)
                Phase 2: Edit individual raw number/text subfields (drawer, row, col, amount, qty)
              Text/Numeric fields: 0-9 enters numbers/multi-tap, USB typing enters characters/capitals,
                                  Backspace deletes, F3 / '.' enters period '.', CLR clears
              ENT: Save / advance subfield / return to browse mode
              ESC / F4: Cancel edit / back to previous phase
        """
        comp_type_opts = list(COMP_TYPE_OPTIONS)
        current_type = self.current_label_data.get("comp_type", "BOB")
        if current_type not in comp_type_opts:
            comp_type_opts.insert(0, current_type)

        current_loc = self.current_label_data.get("location", "Location: Beige Cart, drawer 7")
        current_price = self.current_label_data.get("price", "MSRP: $14.95")

        editable_fields = [
            {
                "key": "comp_type",
                "label": "TYPE",
                "type": "choice",
                "options": comp_type_opts,
                "val": current_type,
            },
            {
                "key": "part_number",
                "label": "PART #",
                "type": "text",
                "val": self.current_label_data.get("part_number", self.current_part_number),
            },
            {
                "key": "mfr_part_number",
                "label": "MFR SKU",
                "type": "text",
                "val": self.current_label_data.get("mfr_part_number", ""),
            },
            {
                "key": "decimal_pn",
                "label": "DB ID",
                "type": "text",
                "val": self.current_label_data.get("decimal_pn", "15.45.35.15"),
            },
            {
                "key": "location",
                "label": "LOC",
                "type": "hierarchical",
                "val": current_loc,
            },
            {
                "key": "price",
                "label": "PRICE",
                "type": "hierarchical",
                "val": current_price,
            },
            {
                "key": "brief_desc",
                "label": "BRIEF",
                "type": "text",
                "val": self.current_label_data.get("brief_desc", ""),
            },
            {
                "key": "category",
                "label": "CAT",
                "type": "text",
                "val": self.current_label_data.get("category", ""),
            },
        ]

        selected_idx = 0
        is_editing = False
        edit_phase = "TEMPLATE"  # "TEMPLATE" or "SUBFIELD"
        subfield_idx = 0

        # Hierarchical state variables
        loc_tmpl_idx, loc_vals = parse_location(current_loc)
        price_tmpl_idx, price_vals = parse_price(current_price)

        input_mgr = MultiTapInput()
        needs_redraw = True
        last_blink_time = time.time()
        cursor_visible = True

        while self.running and self.state == SystemState.DISPLAY_RESULT:
            # 1. Physical switches
            is_print = self.hardware.is_print_pressed()
            is_scan = self.hardware.is_scan_pressed()

            # 2. Keypad & USB keyboard
            keypad_key = self.hardware.read_keypad()
            kbd_key = self.keyboard.read_key()
            key = kbd_key if kbd_key is not None else keypad_key

            # Map global shortcuts when in browse mode
            if not is_editing and key is not None:
                if key in ("p", "P", "PRINT"):
                    is_print = True
                    key = None
                elif key in ("s", "S", "r", "R", "SCAN"):
                    is_scan = True
                    key = None

            # Handle Print
            if is_print:
                logger.info("Print button pressed. Sending edited catalog label to thermal printer.")
                for f in editable_fields:
                    self.current_label_data[f["key"]] = f["val"]
                self.current_part_number = self.current_label_data.get("part_number", self.current_part_number)
                self.printer.print_catalog_label(**self.current_label_data)

            # Handle Scan
            if is_scan:
                logger.info("Scan button pressed. Repeating scan.")
                self.state = SystemState.SCANNING
                break

            # Handle Key Events
            if key:
                cur_field = editable_fields[selected_idx]

                if not is_editing:
                    # --- BROWSE MODE ---
                    if key in ("F1", "UP", "k"):
                        selected_idx = (selected_idx - 1) % len(editable_fields)
                        needs_redraw = True
                    elif key in ("F2", "DOWN", "j"):
                        selected_idx = (selected_idx + 1) % len(editable_fields)
                        needs_redraw = True
                    elif key in ("ENT", "\r", "\n"):
                        is_editing = True
                        if cur_field["key"] == "location":
                            loc_tmpl_idx, loc_vals = parse_location(cur_field["val"])
                            edit_phase = "TEMPLATE"
                        elif cur_field["key"] == "price":
                            price_tmpl_idx, price_vals = parse_price(cur_field["val"])
                            edit_phase = "TEMPLATE"
                        elif cur_field["type"] == "choice":
                            pass
                        else:
                            input_mgr.reset(cur_field["val"])
                        needs_redraw = True
                    elif key in ("F4", "ESC", "q", "Q"):
                        logger.info("F4 / ESC pressed. Returning to IDLE camera view.")
                        self.state = SystemState.IDLE
                        break

                else:
                    # --- EDIT MODE ---
                    # Case A: Location (Hierarchical)
                    if cur_field["key"] == "location":
                        if edit_phase == "TEMPLATE":
                            if key in ("F1", "UP", "LEFT"):
                                loc_tmpl_idx = (loc_tmpl_idx - 1) % len(LOCATION_TEMPLATES)
                                needs_redraw = True
                            elif key in ("F2", "DOWN", "RIGHT"):
                                loc_tmpl_idx = (loc_tmpl_idx + 1) % len(LOCATION_TEMPLATES)
                                needs_redraw = True
                            elif key in ("ENT", "\t", "\r", "\n"):
                                edit_phase = "SUBFIELD"
                                subfield_idx = 0
                                sf = LOCATION_TEMPLATES[loc_tmpl_idx]["subfields"][0]
                                input_mgr.reset(loc_vals.get(sf["key"], sf["default"]))
                                needs_redraw = True
                            elif key in ("F4", "ESC"):
                                is_editing = False
                                needs_redraw = True
                        else:  # SUBFIELD
                            sf = LOCATION_TEMPLATES[loc_tmpl_idx]["subfields"][subfield_idx]
                            if key == "BACKSPACE":
                                input_mgr.backspace()
                                needs_redraw = True
                            elif key == "CLR":
                                input_mgr.clear()
                                needs_redraw = True
                            elif key in ("ENT", "\t", "\r", "\n"):
                                loc_vals[sf["key"]] = input_mgr.get_text()
                                num_sfs = len(LOCATION_TEMPLATES[loc_tmpl_idx]["subfields"])
                                if subfield_idx + 1 < num_sfs:
                                    subfield_idx += 1
                                    next_sf = LOCATION_TEMPLATES[loc_tmpl_idx]["subfields"][subfield_idx]
                                    input_mgr.reset(loc_vals.get(next_sf["key"], next_sf["default"]))
                                else:
                                    cur_field["val"] = format_location(loc_tmpl_idx, loc_vals)
                                    self.current_label_data["location"] = cur_field["val"]
                                    is_editing = False
                                needs_redraw = True
                            elif key in ("F4", "ESC"):
                                edit_phase = "TEMPLATE"
                                needs_redraw = True
                            else:
                                if sf["type"] == "number":
                                    if key in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
                                        input_mgr.append_char(key)
                                        needs_redraw = True
                                    elif len(key) == 1 and key.isdigit():
                                        input_mgr.append_char(key)
                                        needs_redraw = True
                                else:
                                    if len(key) == 1 and ord(key) >= 32:
                                        input_mgr.append_char(key)
                                        needs_redraw = True
                                    elif key in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "F3"):
                                        input_mgr.handle_key(key)
                                        needs_redraw = True

                    # Case B: Price (Hierarchical)
                    elif cur_field["key"] == "price":
                        if edit_phase == "TEMPLATE":
                            if key in ("F1", "UP", "LEFT"):
                                price_tmpl_idx = (price_tmpl_idx - 1) % len(PRICE_TEMPLATES)
                                needs_redraw = True
                            elif key in ("F2", "DOWN", "RIGHT"):
                                price_tmpl_idx = (price_tmpl_idx + 1) % len(PRICE_TEMPLATES)
                                needs_redraw = True
                            elif key in ("ENT", "\t", "\r", "\n"):
                                edit_phase = "SUBFIELD"
                                subfield_idx = 0
                                sf = PRICE_TEMPLATES[price_tmpl_idx]["subfields"][0]
                                input_mgr.reset(price_vals.get(sf["key"], sf["default"]))
                                needs_redraw = True
                            elif key in ("F4", "ESC"):
                                is_editing = False
                                needs_redraw = True
                        else:  # SUBFIELD
                            sf = PRICE_TEMPLATES[price_tmpl_idx]["subfields"][subfield_idx]
                            if key == "BACKSPACE":
                                input_mgr.backspace()
                                needs_redraw = True
                            elif key == "CLR":
                                input_mgr.clear()
                                needs_redraw = True
                            elif key in ("ENT", "\t", "\r", "\n"):
                                price_vals[sf["key"]] = input_mgr.get_text()
                                num_sfs = len(PRICE_TEMPLATES[price_tmpl_idx]["subfields"])
                                if subfield_idx + 1 < num_sfs:
                                    subfield_idx += 1
                                    next_sf = PRICE_TEMPLATES[price_tmpl_idx]["subfields"][subfield_idx]
                                    input_mgr.reset(price_vals.get(next_sf["key"], next_sf["default"]))
                                else:
                                    cur_field["val"] = format_price(price_tmpl_idx, price_vals)
                                    self.current_label_data["price"] = cur_field["val"]
                                    is_editing = False
                                needs_redraw = True
                            elif key in ("F4", "ESC"):
                                edit_phase = "TEMPLATE"
                                needs_redraw = True
                            else:
                                if key in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "F3", "."):
                                    if key == "F3":
                                        input_mgr.append_char(".")
                                    else:
                                        input_mgr.append_char(key)
                                    needs_redraw = True
                                elif len(key) == 1 and (key.isdigit() or key == "."):
                                    input_mgr.append_char(key)
                                    needs_redraw = True

                    # Case C: Choice Field (comp_type)
                    elif cur_field["type"] == "choice":
                        opts = cur_field["options"]
                        cur_val = cur_field["val"]
                        cur_opt_idx = opts.index(cur_val) if cur_val in opts else 0

                        if key in ("F1", "UP", "LEFT"):
                            cur_field["val"] = opts[(cur_opt_idx - 1) % len(opts)]
                            self.current_label_data[cur_field["key"]] = cur_field["val"]
                            needs_redraw = True
                        elif key in ("F2", "DOWN", "RIGHT"):
                            cur_field["val"] = opts[(cur_opt_idx + 1) % len(opts)]
                            self.current_label_data[cur_field["key"]] = cur_field["val"]
                            needs_redraw = True
                        elif key in ("ENT", "\r", "\n", "\t"):
                            is_editing = False
                            self.current_label_data[cur_field["key"]] = cur_field["val"]
                            needs_redraw = True
                        elif key == "CLR":
                            cur_field["val"] = opts[0]
                            self.current_label_data[cur_field["key"]] = cur_field["val"]
                            needs_redraw = True
                        elif key in ("F4", "ESC"):
                            is_editing = False
                            needs_redraw = True

                    # Case D: Text / Numeric Entry (part_number, mfr_part_number, decimal_pn, etc.)
                    else:
                        if key == "BACKSPACE":
                            input_mgr.backspace()
                            needs_redraw = True
                        elif key == "CLR":
                            input_mgr.clear()
                            needs_redraw = True
                        elif key in ("ENT", "\r", "\n", "\t"):
                            cur_field["val"] = input_mgr.get_text()
                            self.current_label_data[cur_field["key"]] = cur_field["val"]
                            if cur_field["key"] == "part_number":
                                self.current_part_number = cur_field["val"]
                            is_editing = False
                            needs_redraw = True
                        elif key in ("F4", "ESC"):
                            is_editing = False
                            needs_redraw = True
                        else:
                            # Typed characters
                            if len(key) == 1 and ord(key) >= 32:
                                input_mgr.append_char(key)
                                needs_redraw = True
                            elif key in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "F3"):
                                input_mgr.handle_key(key)
                                needs_redraw = True

            # 4. Handle cursor blink for text editing fields
            now = time.time()
            if is_editing:
                if now - last_blink_time >= 0.4:
                    cursor_visible = not cursor_visible
                    last_blink_time = now
                    needs_redraw = True

            # 5. Redraw LCD screen if state changed
            if needs_redraw:
                cur_field = editable_fields[selected_idx]
                cursor = "_" if cursor_visible else " "

                # Populate dynamic display strings for hierarchical fields
                if is_editing:
                    if cur_field["key"] == "location":
                        if edit_phase == "TEMPLATE":
                            tmpl_name = LOCATION_TEMPLATES[loc_tmpl_idx]["name"]
                            cur_field["edit_display_str"] = f"◀ {tmpl_name} ▶"
                            cur_field["footer_hint"] = "F1/F2:Template  ENT:Edit numbers  ESC:Cancel"
                        else:
                            tmpl_name = LOCATION_TEMPLATES[loc_tmpl_idx]["name"]
                            sf = LOCATION_TEMPLATES[loc_tmpl_idx]["subfields"][subfield_idx]
                            buf_text = input_mgr.get_text()
                            cur_field["edit_display_str"] = f"{tmpl_name} {sf['label']}: [{buf_text}{cursor}]"
                            cur_field["footer_hint"] = f"Type {sf['label']}  CLR:Clear  ENT:Next/Save  ESC:Back"

                    elif cur_field["key"] == "price":
                        if edit_phase == "TEMPLATE":
                            tmpl_name = PRICE_TEMPLATES[price_tmpl_idx]["name"]
                            cur_field["edit_display_str"] = f"◀ {tmpl_name} ▶"
                            cur_field["footer_hint"] = "F1/F2:Template  ENT:Edit price  ESC:Cancel"
                        else:
                            buf_text = input_mgr.get_text()
                            if price_tmpl_idx == 0:
                                cur_field["edit_display_str"] = f"MSRP: $[{buf_text}{cursor}]"
                                cur_field["footer_hint"] = "0-9/.:Price  CLR:Clear  ENT:Save  ESC:Back"
                            else:
                                if subfield_idx == 0:
                                    cur_qty = price_vals.get("qty", "10")
                                    cur_field["edit_display_str"] = f"MSRP: $[{buf_text}{cursor}]/{cur_qty} units"
                                    cur_field["footer_hint"] = "0-9/.:Price  CLR:Clear  ENT:Next  ESC:Back"
                                else:
                                    cur_amt = price_vals.get("amount", "2.50")
                                    cur_field["edit_display_str"] = f"MSRP: ${cur_amt}/[{buf_text}{cursor}] units"
                                    cur_field["footer_hint"] = "0-9:Units  CLR:Clear  ENT:Save  ESC:Back"

                    elif cur_field["type"] == "choice":
                        cur_field["edit_display_str"] = None
                        cur_field["footer_hint"] = "F1/F2:Cycle  ENT:Save  CLR:Reset  ESC:Cancel"
                    else:
                        cur_field["edit_display_str"] = None
                        cur_field["footer_hint"] = "0-9/Keys:Type  F3/.:Dot  CLR:Clear  ENT:Save  ESC:Cancel"
                else:
                    cur_field["edit_display_str"] = None
                    cur_field["footer_hint"] = None

                edit_buf = input_mgr.get_text() if is_editing else ""
                self.display.show_label_editor(
                    fields=editable_fields,
                    selected_idx=selected_idx,
                    is_editing=is_editing,
                    edit_buffer=edit_buf,
                    cursor_visible=cursor_visible,
                )
                needs_redraw = False

            time.sleep(0.02)

    def _handle_error_state(self) -> None:
        """Error state: displays error details, waits for F4 or Rescan."""
        self.display.show_error("ANALYSIS FAILED", self.last_error_message)

        while self.running and self.state == SystemState.ERROR:
            kbd_key = self.keyboard.read_key()
            if self.hardware.is_scan_pressed() or kbd_key in ("SCAN", "s", "S", "r", "R", " "):
                logger.info("Retrying scan from error state.")
                self.state = SystemState.SCANNING
                break

            if self.hardware.is_f4_pressed() or kbd_key in ("F4", "ESC", "q", "Q"):
                logger.info("Returning to IDLE from error state.")
                self.state = SystemState.IDLE
                break

            time.sleep(0.03)

    def shutdown(self) -> None:
        """Clean shutdown of all hardware resources."""
        logger.info("Shutting down LABRARIAN MK 1...")
        self.running = False
        self.stop_event.set()
        try:
            self.display.show_status("LABRARIAN MK 1", "Shutting down...")
            time.sleep(0.3)
        except Exception:
            pass

        self.camera.release()
        self.printer.close()
        self.hardware.close()
        self.keyboard.close()
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

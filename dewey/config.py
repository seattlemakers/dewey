"""Configuration constants and pin assignments for Dewey."""

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Display (ILI9341 SPI LCD) ---
# 320x240 landscape orientation matching ctest/cam_display.py
LCD_WIDTH = 320
LCD_HEIGHT = 240
LCD_ROTATION = 90
LCD_BAUDRATE = 64_000_000

# Color scheme: black background, all text orange
COLOR_BG = (0, 0, 0)             # Pure Black
COLOR_TEXT = (255, 140, 0)        # Bright Orange
COLOR_DIM_TEXT = (200, 100, 0)    # Subdued Orange for hints/borders

# Font paths with fallbacks
FONT_PATHS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_PATHS_NORMAL = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

FONT_SIZE_LARGE = 22
FONT_SIZE_NORMAL = 13
FONT_SIZE_SMALL = 10

# --- Camera ---
CAMERA_INDEX = int(os.getenv("DEWEY_CAM_INDEX", "0"))
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080

# --- GPIO Inputs ---
# Switches connect to GND, so internal pull-ups are used (active LOW)
PIN_SCAN_SWITCH = 5    # Red switch: Scan / take image
PIN_PRINT_SWITCH = 6   # White switch: Print label

# 4x4 Keypad Matrix (BCM pin numbering)
# Rows: Inputs with pull-ups
KEYPAD_ROWS = [26, 21, 20, 16]
# Cols: Outputs driven LOW sequentially
KEYPAD_COLS = [12, 24, 23, 18]

KEYPAD_MAP = [
    ['F4', 'CLR', '0', 'ENT'],
    ['F3', '7',   '8', '9'],
    ['F2', '4',   '5', '6'],
    ['F1', '1',   '2', '3']
]

# --- Thermal Printer ---
# ESC/POS legacy driver (v2.16 firmware, 19200 baud, TX only on GPIO 14)
PRINTER_PORT = os.getenv("DEWEY_PRINTER_PORT", "/dev/serial0")
PRINTER_BAUDRATE = 19200
PRINTER_CHARS_PER_LINE = 32

# --- Gemini API ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_DESCRIPTION_WORDS = 100

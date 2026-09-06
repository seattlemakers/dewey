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
# Physical paper width in printer dots (58mm paper @ 203 DPI ≈ 384 dots).
PRINTER_DOTS_PER_LINE = int(os.getenv("DEWEY_PRINTER_DOTS_PER_LINE", "384"))

# Heating & Darkness parameters (ESC 7 and DC2 # commands)
# Max heating dots (unit: 8 dots, range 0-255, default 7 = 64 dots)
# Keeping this around 7 (64 dots) ensures the thermal elements get concentrated power.
PRINTER_HEAT_DOTS = int(os.getenv("DEWEY_PRINTER_HEAT_DOTS", "7"))
# Heating time (unit: 10µs, range 3-255; factory default 80; 220-255 gives maximum burn)
PRINTER_HEAT_TIME = int(os.getenv("DEWEY_PRINTER_HEAT_TIME", "220"))
# Heating interval between dot groups (unit: 10µs, range 0-255).
# CRITICAL: This is the COOLING pause between dot groups. If set too high (e.g. 255 = 2.55ms),
# the printhead cools completely down between dot groups, causing faint/dim text.
# 20-40 (200-400µs) keeps the head at optimal burning temperature.
PRINTER_HEAT_INTERVAL = int(os.getenv("DEWEY_PRINTER_HEAT_INTERVAL", "20"))
# Print density (0-31 where 0=50%, 10=100%, 31=205% maximum density)
PRINTER_DENSITY = int(os.getenv("DEWEY_PRINTER_DENSITY", "15"))
# Print break time (0-7 in units of 250µs; 2 = 500µs cooling between lines)
PRINTER_BREAK_TIME = int(os.getenv("DEWEY_PRINTER_BREAK_TIME", "2"))
# DTR pin (BCM): None to disable hardware handshake (prevents GPIO floating/timing glitches)
PRINTER_DTR_PIN: int | None = None

# --- Gemini API ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
MAX_DESCRIPTION_WORDS = 100



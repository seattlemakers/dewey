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

# ===========================================================================
# Thermal Printer Control Parameters: ESC 7 and DC2 # Commands
# ===========================================================================

# ---------------------------------------------------------------------------
# Command: ESC 7 n1 n2 n3 — Setting Control Parameter Command
# Format:
#   ASCII:  ESC        '7'       n1   n2   n3
#   Hex:    0x1B       0x37      n1   n2   n3
#   Python: b'\x1b\x37' + bytes([PRINTER_HEAT_DOTS, PRINTER_HEAT_TIME, PRINTER_HEAT_INTERVAL])
# ---------------------------------------------------------------------------

# Parameter n1 (Byte 3 of ESC 7): Max heating dots
#   Formula: (n1 + 1) * 8 dots fired simultaneously across 384-dot head. Range: 0-255.
#   Default: 7 (64 dots = 1/6 width). Lower values (7-10 = 64-88 dots) limit peak current on 5V supply.
PRINTER_HEAT_DOTS = int(os.getenv("DEWEY_PRINTER_HEAT_DOTS", "2"))  # ESC 7 -> n1: ((n1+1)*8 dots: 2 = 24 dots)

# Parameter n2 (Byte 4 of ESC 7): Heating pulse duration
#   Formula: n2 * 10 µs burn pulse duration per dot group. Range: 3-255.
#   Default: 80 (800 µs). Higher values = darker print, but increases line print time.
PRINTER_HEAT_TIME = int(os.getenv("DEWEY_PRINTER_HEAT_TIME", "255"))  # ESC 7 -> n2: (burn time: n2*10µs: 255 = 2550 µs)

# Parameter n3 (Byte 5 of ESC 7): Heating recovery interval
#   Formula: n3 * 10 µs pause between dot groups on each line. Range: 0-255.
#   Default: 2 (20 µs). Recommended: 20-40 (200-400 µs).
#   CRITICAL: If set too high (e.g. 255 = 2.55 ms), the head cools down completely, causing faint/dim text.
PRINTER_HEAT_INTERVAL = int(os.getenv("DEWEY_PRINTER_HEAT_INTERVAL", "2"))  # ESC 7 -> n3: (recovery pause: n3*10µs: 2 = 20 µs)


# ---------------------------------------------------------------------------
# Command: DC2 # n — Set Printing Density and Break Time
# Format:
#   ASCII:  DC2        '#'       n
#   Hex:    0x12       0x23      n
#   Python: b'\x12\x23' + bytes([((PRINTER_BREAK_TIME & 0x07) << 5) | (PRINTER_DENSITY & 0x1F)])
# ---------------------------------------------------------------------------

# Parameter n, Bits 4..0 (D4-D0 of DC2 #): Print density
#   Formula: Density = 50% + 5% * n[D4..D0]. Range: 0-31 (0x00 - 0x1F).
#   Values: 0 = 50% (lightest), 10 = 100% (normal), 15 = 125%, 31 = 205% (maximum darkness).
PRINTER_DENSITY = int(os.getenv("DEWEY_PRINTER_DENSITY", "31"))  # DC2 # -> n bits 4..0: (density: 50% + 5%*n: 10 = 100%)

# Parameter n, Bits 7..5 (D7-D5 of DC2 #): Inter-line break time
#   Formula: Break Time = n[D7..D5] * 250 µs cooling wait between printing lines. Range: 0-7 (0x00 - 0x07, shifted << 5).
#   Values: 0 = 0 µs, 2 = 500 µs, 7 = 1750 µs.
PRINTER_BREAK_TIME = int(os.getenv("DEWEY_PRINTER_BREAK_TIME", "2"))  # DC2 # -> n bits 7..5: (break time: n*250µs: 2 = 500 µs)

# DTR pin (BCM): None to disable hardware handshake (prevents GPIO floating/timing glitches)
PRINTER_DTR_PIN: int | None = None

# --- Gemini API ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
MAX_DESCRIPTION_WORDS = 100



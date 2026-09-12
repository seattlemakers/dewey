"""Printer label test for DFRobot Embedded Thermal Printer V2.0 (DFR0503-EN).

Tests printing the full component catalog label specified in label_format.md
using factory default printer settings in both modes:
  1. Native ESC/POS Text Mode (buffer-safe, sharp hardware fonts)
  2. Bitmap Graphics Mode (Pillow-rendered TrueType monospace layout)
"""

import os
import sys
import time

# Allow importing from the project root when run directly from ctest/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dewey import config
from dewey.thermal_printer import ThermalPrinter

LABEL_DATA = {
    "comp_type": "BOB",
    "part_number": "FT232H",
    "mfr_part_number": "(Adafruit 2264)",
    "brief_desc": "FT232H Breakout: General Purpose USB to GPIO, SPI, I2C",
    "category": "ICs > Serial > USB > USB Converters > USB to GPIO",
    "decimal_pn": "15.45.35.15",
    "location": "Location: Beige Cart, drawer 7",
    "price": "MSRP: $14.95",
    "date_updated": "2026-09-11",
    "description": (
        "Single-channel USB 2.0 Hi-Speed (480Mbps) to UART, FIFO, I2C, SPI, JTAG, "
        "and GPIO interface breakout board. Powered via 5V USB with an onboard 3.3V "
        "regulator; digital I/O pins operate at 3.3V logic and are 5V tolerant. "
        "Delivers up to 500mA from USB and 50mA from 3.3V rail with configurable 4mA "
        "to 16mA pin drive. Multi-Protocol Synchronous Serial Engine simplifies "
        "hardware bus emulation. Fully compatible with Python (via pyFTDI and "
        "Adafruit Blinka), C/C++, and CircuitPython across Linux, macOS, and Windows. "
        "Warning: External pull-up resistors (4.7kΩ) are required on SDA/SCL for I2C "
        "operation. Avoid exceeding 3.3V on power rails without proper regulation."
    ),
}

def main():
    print("=" * 60)
    print("  DFRobot Embedded Thermal Printer V2.0 - Label Test")
    print("=" * 60)
    print(f"Port:                    {config.PRINTER_PORT}")
    print(f"Baud rate:               {config.PRINTER_BAUDRATE}")
    print(f"Dots per line:           {config.PRINTER_DOTS_PER_LINE}")
    print(f"Default settings:        {config.PRINTER_USE_DEFAULT_SETTINGS}")
    print("=" * 60)

    print("\nInitializing printer with factory default settings (ESC @)...")
    printer = ThermalPrinter()
    print("Printer initialized.\n")

    # 1. Native ESC/POS Text Mode Label
    print("--> 1/2: Printing catalog label in Native ESC/POS Text Mode...")
    printer.print_catalog_label(**LABEL_DATA, mode="text")
    print("    Text mode label sent.")

    # Brief delay between test prints
    time.sleep(1.0)

    # 2. Bitmap Graphics Mode Label
    print("--> 2/2: Printing catalog label in Bitmap Graphics Mode...")
    printer.print_catalog_label(**LABEL_DATA, mode="bitmap")
    print("    Bitmap mode label sent.")

    printer.close()
    print("\n" + "=" * 60)
    print("All label tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()

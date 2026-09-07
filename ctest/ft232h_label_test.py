"""Printer test script for the Adafruit FT232H breakout label.

Prints the complete catalog label specified in label_format.md:
  - Line 1:   Component type (BOB, double-size, bold, inverse) + Part number (FT232H, double-size, normal)
  - Line 1.5: Manufacturer part number (Adafruit 2264)
  - Line 2:   Brief description (Bold, max 64 chars / 2 lines)
  - Line 3:   Human-readable category (Normal)
  - Line 4:   Database decimal part number (Normal)
  - Line 5:   Location (Normal)
  - Line 6:   Price (Bold)
  - Line 7:   100-word detailed description (Normal)

Prints ASCII text mode first, followed by Bitmap graphics mode (Pillow-rendered fonts).
"""

import os
import sys
import time

# Allow importing from the project root when run directly from ctest/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dewey.thermal_printer import LegacyThermalPrinter

LABEL_DATA = {
    "comp_type": "BOB",
    "part_number": "FT232H",
    "mfr_part_number": "(Adafruit 2264)",
    "brief_desc": "FT232H Breakout: General Purpose USB to GPIO, SPI, I2C",
    "category": "ICs > Serial > USB > USB Converters > USB to GPIO",
    "decimal_pn": "15.45.35.15",
    "location": "Location: Beige Cart, drawer 7",
    "price": "MSRP: $14.95",
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
    print("Connecting to thermal printer...")
    printer = LegacyThermalPrinter()

    # Determine mode: default to printing both (ASCII first, then Bitmap)
    requested_mode = sys.argv[1].lower() if len(sys.argv) > 1 else "both"

    if requested_mode in ("both", "text", "ascii"):
        print("\n--- Printing FT232H Label (1/2: Native ESC/POS Text Mode) ---")
        printer.print_catalog_label(**LABEL_DATA, mode="text")

    if requested_mode in ("both", "bitmap", "image"):
        if requested_mode == "both":
            time.sleep(0.5)
        print("\n--- Printing FT232H Label (2/2: Bitmap Graphics Mode) ---")
        printer.print_catalog_label(**LABEL_DATA, mode="bitmap")

    printer.close()
    print("\nFT232H label test completed successfully!")

if __name__ == "__main__":
    main()

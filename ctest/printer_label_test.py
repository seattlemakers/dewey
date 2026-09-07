"""Printer label test — prints an example component label using all
printer parameters defined in dewey/config.py."""

import os
import sys

print("test...")

# Allow importing from the project root when run directly from ctest/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dewey import config
from dewey.thermal_printer import LegacyThermalPrinter

print(f"Active parameters from dewey/config.py:")
print(f"  • ESC 7: dots={config.PRINTER_HEAT_DOTS} ({(config.PRINTER_HEAT_DOTS+1)*8} dots), "
      f"heat_time={config.PRINTER_HEAT_TIME} ({config.PRINTER_HEAT_TIME*10}µs), "
      f"interval={config.PRINTER_HEAT_INTERVAL} ({config.PRINTER_HEAT_INTERVAL*10}µs)")
print(f"  • DC2 #: density={config.PRINTER_DENSITY} ({50+5*config.PRINTER_DENSITY}%), "
      f"break_time={config.PRINTER_BREAK_TIME} ({config.PRINTER_BREAK_TIME*250}µs)")

printer = LegacyThermalPrinter()
print("Printer initialized and parameters applied.")

# 1. First print: Native ASCII text mode
print("1/2: Printing component label in ASCII mode...")
printer.print_component_label(
    part_number="LM358P",
    description=(
        "Dual general-purpose op-amp, DIP-8, "
        "3V-32V supply, 1MHz GBW. "
        "Bin: A3 / Drawer 12."
    ),
    mode="text",
)

# 2. Second print: Bitmap graphics mode (Pillow-rendered system fonts)
print("2/2: Printing component label in Bitmap mode...")
printer.print_component_label(
    part_number="LM358P",
    description=(
        "Dual general-purpose op-amp, DIP-8, "
        "3V-32V supply, 1MHz GBW. "
        "Bin: A3 / Drawer 12."
    ),
    mode="bitmap",
)

printer.close()
print("All label tests completed successfully.")

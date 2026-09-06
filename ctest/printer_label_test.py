"""Printer label test — prints an example component label using all
printer parameters defined in dewey/config.py."""

import os
import sys

# Allow importing from the project root when run directly from ctest/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dewey.thermal_printer import LegacyThermalPrinter

# LegacyThermalPrinter reads all settings (port, baudrate, heat dots,
# heat time, heat interval, density, break time) directly from config.py,
# so no arguments are needed here.
printer = LegacyThermalPrinter()

printer.print_component_label(
    part_number="LM358P",
    description=(
        "Dual general-purpose op-amp, DIP-8, "
        "3V-32V supply, 1MHz GBW. "
        "Bin: A3 / Drawer 12."
    ),
)

printer.close()
print("Label test completed successfully.")

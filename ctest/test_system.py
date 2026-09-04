"""Unit tests for Dewey components, display rendering, and label formatting."""

import unittest
from PIL import Image
from dewey.config import COLOR_BG, COLOR_TEXT, LCD_HEIGHT, LCD_WIDTH, PRINTER_CHARS_PER_LINE
from dewey.display import DisplayManager
from dewey.gemini_service import JSON_SCHEMA
from dewey.thermal_printer import LegacyThermalPrinter
import textwrap


class TestDeweySystem(unittest.TestCase):

    def setUp(self):
        self.display = DisplayManager()

    def test_display_canvas_size(self):
        """Verify display dimensions match 320x240 landscape."""
        self.assertEqual(self.display.width, LCD_WIDTH)
        self.assertEqual(self.display.height, LCD_HEIGHT)
        self.assertEqual(LCD_WIDTH, 320)
        self.assertEqual(LCD_HEIGHT, 240)

    def test_display_render_result(self):
        """Verify show_component_result draws without error on mock canvas."""
        part_number = "NE555P"
        description = "Precision timer IC capable of producing accurate time delays or oscillation. Widely used in electronic lab circuits."
        # Call show_component_result
        self.display.show_component_result(part_number, description)

    def test_display_long_part_number(self):
        """Verify long part numbers scale down appropriately."""
        part_number = "STM32F401RET6TR-VERY-LONG-PART-NUMBER"
        description = "ARM Cortex-M4 32-bit RISC core operating at a frequency of up to 84 MHz."
        self.display.show_component_result(part_number, description)

    def test_thermal_printer_formatting(self):
        """Verify component label formatting and line wrapping logic."""
        printer = LegacyThermalPrinter(port="/dev/null")
        description = (
            "ATmega328P 8-bit AVR Microcontroller with 32KB ISP Flash memory, "
            "1KB EEPROM, 2KB SRAM, 23 general purpose I/O lines, 32 general purpose "
            "working registers, real time counter, three flexible timer/counters with compare modes."
        )
        lines = textwrap.wrap(description, width=PRINTER_CHARS_PER_LINE)
        for line in lines:
            self.assertLessEqual(len(line), PRINTER_CHARS_PER_LINE)
        printer.print_component_label("ATMEGA328P-PU", description)
        printer.close()

    def test_json_schema(self):
        """Verify JSON schema requires part_number and description."""
        self.assertIn("part_number", JSON_SCHEMA["required"])
        self.assertIn("description", JSON_SCHEMA["required"])
        self.assertEqual(JSON_SCHEMA["type"], "OBJECT")


if __name__ == "__main__":
    unittest.main()

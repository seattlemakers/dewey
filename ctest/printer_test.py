# Simple demo of printer functionality using dewey_thermal LegacyThermalPrinter.
import os
import sys

# Allow importing dewey_thermal when run from root or ctest directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dewey_thermal import LegacyThermalPrinter

# Initialize the printer connection
printer = LegacyThermalPrinter(port="/dev/serial0", baudrate=19200)

print("Printer initialized")

# Move the paper forward two lines:
printer.feed(2)

# Print a line of text:
printer.write_line("Hello world!")

printer.feed(2)

# Print a bold line of text:
printer.set_bold(True)
printer.write_line("Bold hello world!")
printer.set_bold(False)

# Print an underline line of text:
printer.set_underline(True)
printer.write_line("Underline text!")
printer.set_underline(False)

# Print an inverted line:
printer.set_invert(True)
printer.write_line("Inverse hello world!")
printer.set_invert(False)

# Print a double height line:
printer.set_size("double_height")
printer.write_line("Double height!")
printer.set_size("normal")

# Print a double width line:
printer.set_size("double_width")
printer.write_line("Double width!")
printer.set_size("normal")

# Print large size text:
printer.set_size("large")
printer.write_line("Large size text!")

# Back to normal / small size text:
printer.set_size("normal")

# Print center justified text:
printer.set_justification("center")
printer.write_line("Center justified!")

# Print right justified text:
printer.set_justification("right")
printer.write_line("Right justified!")

# Back to left justified / normal text:
printer.set_justification("left")

# Print a UPC barcode:
printer.write_line("UPCA barcode:")
printer.print_barcode("123456789012", system="UPC-A")

# Print a bitmap graphic (solid stripe, 384x8 pixels):
printer.feed(1)
solid_stripe = [0xFF] * 48  # 48 bytes * 8 bits = 384 pixel width
printer.print_bitmap(width=384, height=8, data_bytes=solid_stripe)

# Feed a few lines to see everything and close cleanly:
printer.feed(2)
printer.close()

print("Print test completed successfully.")


import time
from dewey_thermal import LegacyThermalPrinter

# 1. Initialize the custom driver class over the locked GPIO serial connection
printer = LegacyThermalPrinter(port='/dev/serial0', baudrate=19200)

# 2. Text Effects & Sizing Demonstration
printer.set_justification('center')
printer.set_size('large')
printer.write_line("DEWEY SYSTEM")
printer.set_size('normal')
printer.write_line("Library Check-Out System")
printer.feed(1)

printer.set_justification('left')
printer.set_bold(True)
printer.write_line("Item Status Report:")
printer.set_bold(False)

# Mix styles inline by issuing commands between lines
printer.write_line("Title: Introduction to Python")
printer.set_underline(True)
printer.write_line("Due Date: Friday, September 11, 2026")
printer.set_underline(False)

# White-on-Black Badge style
printer.set_justification('center')
printer.set_invert(True)
printer.write_line("  VERIFIED RETURN  ")
printer.set_invert(False)
printer.feed(1)

# 3. Barcode Demonstration
# Legacy firmware prints barcodes natively using 'UPC-A', 'CODE39', or 'EAN13'.
# Note: For UPC-A, data must be exactly 11 or 12 numerical digits.
printer.write_line("[Item Serial ID]")
printer.print_barcode("123456789012", system='UPC-A')
printer.feed(2)

# 4. Graphics Overview
# To print a custom logo or image, you need to turn your graphic into a 1-bit vertical 
# byte array that is exactly 384 pixels wide. For example, a tiny solid black square 
# (384 pixels wide by 8 pixels high) can be constructed like this:
solid_black_stripe = [0xFF] * 48 # 48 bytes * 8 bits = 384 pixel width
printer.print_bitmap(width=384, height=8, data_bytes=solid_black_stripe)

# Safe completion and clean tear feed
printer.feed(3)
printer.close()
print("Print job complete!")

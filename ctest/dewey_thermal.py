# dewey_thermal.py
# A lightweight, standalone Python driver for legacy Adafruit/ESC-POS thermal printers
# designed specifically for older firmware variants (e.g., v2.16.x).

import serial
import time

class LegacyThermalPrinter:
    def __init__(self, port='/dev/serial0', baudrate=19200, timeout=1):
        """Initializes the serial connection and resets the printer."""
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        time.sleep(0.5)
        self.reset()

    def reset(self):
        """Resets the printer memory settings to defaults."""
        self.ser.write(b'\x1b\x40')
        time.sleep(0.1)

    def write_line(self, text):
        """Prints a standard string line encoded in ASCII/CP437 layout."""
        self.ser.write(text.encode('ascii', errors='ignore') + b'\n')

    def feed(self, lines=1):
        """Feeds the paper by a specified number of lines."""
        for _ in range(lines):
            self.ser.write(b'\n')

    # --- TEXT EFFECTS ---
    def set_bold(self, enabled=True):
        """Turns Bold on or off (ESC E n)."""
        val = b'\x01' if enabled else b'\x00'
        self.ser.write(b'\x1b\x45' + val)

    def set_underline(self, enabled=True):
        """Turns Underline on or off (ESC - n)."""
        val = b'\x01' if enabled else b'\x00'
        self.ser.write(b'\x1b\x2d' + val)

    def set_invert(self, enabled=True):
        """Turns White-on-Black inverse text mode on or off (GS B n)."""
        val = b'\x01' if enabled else b'\x00'
        self.ser.write(b'\x1d\x42' + val)

    # --- JUSTIFICATION ---
    def set_justification(self, align='left'):
        """Aligns text: 'left', 'center', or 'right' (ESC a n)."""
        align = align.lower()
        if align == 'left':
            self.ser.write(b'\x1b\x61\x00')
        elif align == 'center':
            self.ser.write(b'\x1b\x61\x01')
        elif align == 'right':
            self.ser.write(b'\x1b\x61\x02')

    # --- TEXT SIZING ---
    def set_size(self, size='normal'):
        """Sets character sizing using standard GS ! formatting options."""
        size = size.lower()
        if size == 'normal':
            self.ser.write(b'\x1d\x21\x00') # Normal 1x Width, 1x Height
        elif size == 'double_height':
            self.ser.write(b'\x1d\x21\x01') # 1x Width, 2x Height
        elif size == 'double_width':
            self.ser.write(b'\x1d\x21\x10') # 2x Width, 1x Height
        elif size == 'large':
            self.ser.write(b'\x1d\x21\x11') # 2x Width, 2x Height

    # --- BARCODES ---
    def print_barcode(self, data, system='UPC-A'):
        """Prints a barcode based on legacy firmware rules (GS k m data NUL)."""
        system = system.upper()
        
        # Safe structural dictionary mapping common legacy barcode systems
        systems = {
            'UPC-A': b'\x00',
            'UPC-E': b'\x01',
            'EAN13': b'\x02',
            'EAN8':  b'\x03',
            'CODE39': b'\x04',
        }
        
        if system not in systems:
            raise ValueError(f"Unsupported legacy barcode system: {system}")
            
        # Command format: GS k [system_byte] [data_bytes] [NUL_terminator]
        cmd = b'\x1d\x6b' + systems[system] + data.encode('ascii') + b'\x00'
        self.ser.write(cmd)
        time.sleep(0.1)

    # --- GRAPHICS / BITMAPS ---
    def print_bitmap(self, width, height, data_bytes):
        """Prints raw 1-bit bitmap data using the legacy ESC * command.
        width: Must be exactly 384 pixels for Adafruit PID 597 printers.
        height: The total vertical pixels.
        data_bytes: A flat bytearray/list where 1 bit = 1 pixel (8 vertical pixels per byte).
        """
        if width != 384:
            raise ValueError("Adafruit legacy mini printer must be exactly 384 pixels wide.")
            
        # ESC * m nL nH [data] command parameters
        # For legacy 8-dot single density bitmap printing:
        # m = 0 (8-dot single-density mode)
        # width = 384 total pixels. nL, nH = width % 256, width // 256
        # 384 % 256 = 128 (\x80), 384 // 256 = 1 (\x01)
        
        # Chop the image data up into 8-pixel high horizontal stripes
        bytes_per_row = width // 8
        stripes = height // 8
        
        for stripe in range(stripes):
            # Send the header sequence for an 8-dot vertical stripe
            self.ser.write(b'\x1b\x2a\x00\x80\x01')
            
            # Extract and stream data bytes corresponding to this specific stripe row
            start_idx = stripe * bytes_per_row
            end_idx = start_idx + bytes_per_row
            self.ser.write(bytes(data_bytes[start_idx:end_idx]))
            
            # Send line feed and allow memory overhead buffer time
            self.ser.write(b'\n')
            time.sleep(0.02)

    def close(self):
        """Closes the serial line hardware safely."""
        self.ser.close()

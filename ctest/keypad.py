#!/usr/bin/env python3
import time
from gpiozero import DigitalInputDevice, DigitalOutputDevice

class Keypad4x4:
    def __init__(self, row_pins, col_pins):
        """
        Initializes the 4x4 keypad matrix with static pin definitions.
        """
        self.row_pins = row_pins
        self.col_pins = col_pins
        
        self.KEYMAP = [
            ['F4', 'CLR', '0', 'ENT'],
            ['F3', '7', '8', '9'],
            ['F2', '4', '5', '6'],
            ['F1', '1', '2', '3']
        ]
        
        # Track the key that was pressed in the previous scan cycle
        self.last_key_pressed = None
        
        # Initialize Rows (Inputs with Pull-ups) and Columns (Outputs starting HIGH)
        self.rows = [DigitalInputDevice(pin, pull_up=True) for pin in self.row_pins]
        self.cols = [DigitalOutputDevice(pin, active_high=True, initial_value=True) for pin in self.col_pins]

    def scan_matrix(self):
        """
        Internal low-level scan. Returns the key currently physically closed, or None.
        """
        for col_idx, col_device in enumerate(self.cols):
            col_device.off()  # Drive column LOW (0V)
            time.sleep(0.001) # Electrical stabilization buffer
            
            for row_idx, row_device in enumerate(self.rows):
                if row_device.is_active: # Logic True when physically pulled LOW
                    col_device.on()  # Set column HIGH before returning
                    return self.KEYMAP[row_idx][col_idx]
            
            col_device.on()  # Revert column to HIGH (3.3V)
        return None

    def read_key(self):
        """
        Interfacing function. Emits a character ONLY on the initial press event.
        Returns None if no new key event occurred, or if a key is being held down.
        """
        current_key = self.scan_matrix()
        
        # Case 1: No key is physically pressed right now
        if current_key is None:
            self.last_key_pressed = None
            return None
            
        # Case 2: A key is pressed, and it is the exact same one as the last scan (Held Down)
        if current_key == self.last_key_pressed:
            return None
            
        # Case 3: A new key press event has just been detected
        # Double-check scan (Debounce) to confirm it wasn't an electrical glitch
        time.sleep(0.02)
        confirm_key = self.scan_matrix()
        
        if confirm_key == current_key:
            self.last_key_pressed = current_key
            return current_key
            
        return None


# --- Debug & Execution Block ---
if __name__ == "__main__":
    # Correct GPIO assignments for your setup
    ROWS = [26, 21, 20, 16]
    COLS = [12, 24, 23, 18]
    
    print("[INFO] Initializing 4x4 Keypad Matrix Interface...")
    keypad = Keypad4x4(row_pins=ROWS, col_pins=COLS)
    print("[INFO] Keypad ready. Press and hold keys to verify single-character emission.")
    
    try:
        while True:
            key = keypad.read_key()
            
            if key is not None:
                print(f"[DEBUG] Key Pressed: {key}")
                
            time.sleep(0.02)  # High-frequency scanning loop
            
    except KeyboardInterrupt:
        print("\n[INFO] Exiting debugger script.")

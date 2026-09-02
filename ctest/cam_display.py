import digitalio
import board
from PIL import Image
import cv2
from adafruit_rgb_display import ili9341

# 1. Define hardware pins for Adafruit breakout configuration
cs_pin = digitalio.DigitalInOut(board.CE0)
dc_pin = digitalio.DigitalInOut(board.D25)    # GPIO 25
reset_pin = digitalio.DigitalInOut(board.D24) # GPIO 24

# 2. Initialize SPI bus and the Adafruit ILI9341 display
spi = board.SPI()
disp = ili9341.ILI9341(
    spi,
    rotation=90,  # 90 or 270 for landscape camera view
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=64000000  # High baudrate for maximum SPI speed on Pi 3
)

# 3. Initialize the USB camera (typically /dev/video0)
cap = cv2.VideoCapture(0)

# Set camera capture resolution
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

print("Starting camera stream. Press Ctrl+C to stop.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        # OpenCV reads BGR; convert it to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Convert to a PIL Image
        image = Image.fromarray(rgb_frame)
        
        # 1. Resize to match the physical display controller canvas (240x320)
        image = image.resize((disp.height, disp.width), Image.Resampling.BILINEAR)
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
        image = image.transpose(Image.FLIP_LEFT_RIGHT)

        # 2. Rotate the PIL image 90 degrees to align with landscape hardware mapping
        image = image.rotate(0, expand=True)

        # Draw the frame onto the Adafruit display
        disp.image(image)

except KeyboardInterrupt:
    print("\nStopping stream.")
finally:
    cap.release()


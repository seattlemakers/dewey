"""Camera management for live LCD preview and high-resolution still capture."""

import io
import logging
from typing import Optional, Tuple
from PIL import Image

try:
    import cv2
except ImportError:
    cv2 = None

from dewey.config import CAMERA_HEIGHT, CAMERA_INDEX, CAMERA_WIDTH

logger = logging.getLogger(__name__)


class CameraManager:
    """Manages the USB webcam for live preview and high-resolution snapshots."""

    def __init__(self, device_index: int = CAMERA_INDEX, width: int = CAMERA_WIDTH, height: int = CAMERA_HEIGHT):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.cap: Optional["cv2.VideoCapture"] = None
        self._init_camera()

    def _init_camera(self) -> None:
        if cv2 is None:
            logger.warning("OpenCV (cv2) is not installed. Camera running in mock mode.")
            return

        try:
            self.cap = cv2.VideoCapture(self.device_index)
            if not self.cap.isOpened():
                logger.warning("Could not open video device %d. Running in mock camera mode.", self.device_index)
                self.cap = None
                return

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            logger.info("Camera %d initialized at %dx%d.", self.device_index, self.width, self.height)
        except Exception as err:
            logger.warning("Failed to initialize camera: %s", err)
            self.cap = None

    def read_preview_frame(self) -> Optional[Image.Image]:
        """Reads a frame from the camera and returns a PIL Image in RGB format."""
        if not self.cap or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_frame)

    def capture_high_res_jpeg(self) -> Optional[bytes]:
        """Captures a clean full-resolution still frame and returns JPEG bytes."""
        if not self.cap or not self.cap.isOpened():
            # Return a mock JPEG image for testing if camera is absent
            mock_img = Image.new("RGB", (640, 480), color=(30, 30, 30))
            buf = io.BytesIO()
            mock_img.save(buf, format="JPEG")
            return buf.getvalue()

        # Flush buffer by grabbing 2 frames to ensure the freshest exposure/focus
        for _ in range(2):
            self.cap.grab()

        ret, frame = self.cap.read()
        if not ret or frame is None:
            logger.error("Failed to read high-res snapshot from camera.")
            return None

        ret, jpeg_buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ret:
            logger.error("Failed to encode frame to JPEG.")
            return None

        return bytes(jpeg_buffer)

    def release(self) -> None:
        """Releases the camera device."""
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            logger.info("Camera released.")

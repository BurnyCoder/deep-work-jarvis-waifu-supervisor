# Webcam single-frame capture via OpenCV (requirement 3). The camera is
# opened, read once, and released every cycle so the webcam LED is not lit
# between captures and other apps can use the camera.
# VideoCapture docs: https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html

import logging

import cv2
from PIL import Image

log = logging.getLogger(__name__)


def frame_to_image(frame) -> Image.Image:
    # OpenCV frames are numpy arrays in BGR channel order; cvtColor reorders
    # to RGB for Pillow (https://docs.opencv.org/4.x/d8/d01/group__imgproc__color__conversions.html)
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def capture_webcam() -> Image.Image | None:
    """One webcam frame, or None when unavailable (non-fatal by design)."""
    # CAP_DSHOW forces the DirectShow backend on Windows — the default MSMF
    # backend is known to take seconds to open the device:
    # https://github.com/opencv/opencv/issues/17687
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    try:
        ok, frame = cap.read()                    # ok=False → no usable frame
        if not ok:
            # Webcam busy/absent must never break the monitoring loop —
            # the stitched image simply omits the webcam tile.
            log.warning("webcam capture failed (device busy or absent)")
            return None
        return frame_to_image(frame)
    finally:
        cap.release()                             # free device + turn LED off

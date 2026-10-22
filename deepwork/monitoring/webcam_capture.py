# Webcam single-frame capture via OpenCV (requirement 3). The camera is
# opened, read once, and released every cycle so this app does not retain its
# capture handle between ticks. LED behavior and device sharing depend on the
# camera, driver, and other applications; release does not guarantee either.
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
    """Return one frame or None for a failed read; capture exceptions propagate."""
    # Request DirectShow on Windows. The linked issue reports slow MSMF startup
    # on some configurations; it is not a timing guarantee for every device:
    # https://github.com/opencv/opencv/issues/17687
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    try:
        ok, frame = cap.read()                    # ok=False → no usable frame
        if not ok:
            # A false read result omits the webcam tile; exceptions still fail
            # the capture tick and are reported by the scheduler.
            log.warning("webcam capture failed (device busy or absent)")
            return None
        return frame_to_image(frame)
    finally:
        cap.release()                             # close this capture handle

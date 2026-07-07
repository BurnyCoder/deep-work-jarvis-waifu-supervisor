# Tests for monitoring/screen_capture.py, webcam_capture.py and stitcher.py.
# Hardware calls (real screens/camera) can't run in CI, so we test the pure
# conversion helpers with fakes and the stitcher with tiny in-memory images;
# real capture is exercised by `main.py --smoke` (documented in README).

import numpy as np
from PIL import Image

from deepwork.monitoring.screen_capture import grab_to_image
from deepwork.monitoring.stitcher import stitch
from deepwork.monitoring.webcam_capture import frame_to_image


class FakeGrab:
    # Mimics mss.base.ScreenShot: .size (width, height) and .bgra bytes —
    # exactly what Image.frombuffer consumes in the documented mss→PIL recipe:
    # https://python-mss.readthedocs.io/examples.html#pil
    def __init__(self, w, h, b, g, r):
        self.size = (w, h)
        self.bgra = bytes([b, g, r, 255]) * (w * h)


def test_grab_to_image_converts_bgra_to_rgb():
    img = grab_to_image(FakeGrab(2, 2, b=255, g=0, r=0))   # pure-blue BGRA
    assert img.size == (2, 2) and img.mode == "RGB"
    assert img.getpixel((0, 0)) == (0, 0, 255)             # blue in RGB order


def test_frame_to_image_converts_bgr_ndarray():
    # OpenCV frames are HxWx3 uint8 in BGR channel order:
    # https://docs.opencv.org/4.x/db/d64/tutorial_load_save_image.html
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    frame[:, :] = (255, 0, 0)                              # blue in BGR
    img = frame_to_image(frame)
    assert img.mode == "RGB" and img.getpixel((0, 0)) == (0, 0, 255)


def test_stitch_builds_labeled_grid():
    tiles = [("Monitor 1", Image.new("RGB", (400, 300), "white")),
             ("Monitor 2", Image.new("RGB", (800, 600), "gray")),
             ("Webcam", Image.new("RGB", (320, 240), "black"))]
    canvas = stitch(tiles, caption="2026-07-07 09:00:00")
    # All tiles are scaled to one fixed width and stacked with label bars,
    # so the canvas is exactly tile-width wide and taller than any one tile.
    assert canvas.mode == "RGB"
    assert canvas.width == 960                             # stitcher TILE_W
    assert canvas.height > 300


def test_stitch_single_image_still_works():
    canvas = stitch([("Webcam", Image.new("RGB", (100, 100), "red"))], caption="t")
    assert canvas.width == 960 and canvas.height >= 100

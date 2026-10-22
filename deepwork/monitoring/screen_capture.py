# Multi-monitor screenshot capture via mss — chosen because it is pure
# ctypes (no heavy deps), fast, and enumerates monitors directly:
# https://python-mss.readthedocs.io/stable/usage.html

import logging

# mss grabs raw BGRA screen bytes: https://github.com/BoboTiG/python-mss
import mss
from PIL import Image

log = logging.getLogger(__name__)


def grab_to_image(grab) -> Image.Image:
    # Documented mss→Pillow recipe: the grab exposes .size and .bgra, and
    # Image.frombuffer with raw mode "BGRX" reads BGRA bytes as RGB (the X
    # ignores alpha): https://python-mss.readthedocs.io/stable/examples.html#pil
    return Image.frombuffer("RGB", grab.size, grab.bgra, "raw", "BGRX")


def capture_monitors() -> list[Image.Image]:
    """One PIL image per physical monitor (requirement 3: all monitors)."""
    # This per-call context releases capture resources promptly. MSS 10.2 also
    # supports sharing an instance across threads; a fresh object is our choice,
    # not a thread-safety requirement:
    # https://python-mss.readthedocs.io/stable/usage.html#multithreading
    with mss.mss() as sct:
        # sct.monitors[0] is the virtual bounding box of ALL screens;
        # [1:] are the physical monitors — indexing documented at
        # https://python-mss.readthedocs.io/stable/api.html
        images = [grab_to_image(sct.grab(mon)) for mon in sct.monitors[1:]]
    log.info("captured %d monitor(s)", len(images))
    return images

# Multi-monitor screenshot capture via mss — chosen because it is pure
# ctypes (no heavy deps), fast, and enumerates monitors directly:
# https://python-mss.readthedocs.io/usage.html

import logging

# mss grabs raw BGRA screen bytes: https://github.com/BoboTiG/python-mss
import mss
from PIL import Image

log = logging.getLogger(__name__)


def grab_to_image(grab) -> Image.Image:
    # Documented mss→Pillow recipe: the grab exposes .size and .bgra, and
    # Image.frombuffer with raw mode "BGRX" reads BGRA bytes as RGB (the X
    # ignores alpha): https://python-mss.readthedocs.io/examples.html#pil
    return Image.frombuffer("RGB", grab.size, grab.bgra, "raw", "BGRX")


def capture_monitors() -> list[Image.Image]:
    """One PIL image per physical monitor (requirement 3: all monitors)."""
    # Context manager releases X/Win32 handles; a FRESH instance per call is
    # the documented thread-safe pattern (the monitor thread calls this):
    # https://python-mss.readthedocs.io/usage.html#command-line
    with mss.mss() as sct:
        # sct.monitors[0] is the virtual bounding box of ALL screens;
        # [1:] are the physical monitors — indexing documented at
        # https://python-mss.readthedocs.io/api.html#mss.base.MSSBase.monitors
        images = [grab_to_image(sct.grab(mon)) for mon in sct.monitors[1:]]
    log.info("captured %d monitor(s)", len(images))
    return images

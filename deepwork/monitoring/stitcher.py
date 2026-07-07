# Stitcher — combines monitor screenshots + webcam photo into ONE labeled
# composite (requirement 3: "stitch all captures into a single labeled
# image") so each vision API call sends a single picture per capture moment.
# Pillow drawing docs: https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html

from PIL import Image, ImageDraw

# All tiles are scaled to this width; 960 px keeps text on screenshots
# legible to the vision model while keeping the JPEG payload small.
TILE_W = 960
LABEL_H = 24            # black bar above each tile holding its label text


def stitch(tiles: list[tuple[str, Image.Image]], caption: str) -> Image.Image:
    """Stack labeled tiles vertically into one RGB canvas.

    tiles: (label, image) pairs, e.g. ("Monitor 1", <img>), ("Webcam", <img>).
    caption: timestamp line drawn at the very top of the canvas.
    """
    # Scale each tile to TILE_W preserving aspect ratio — one readable line
    # per tile using Image.resize (https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize)
    scaled = [(label, img.resize((TILE_W, max(1, round(img.height * TILE_W / img.width)))))
              for label, img in tiles]
    # Total height = caption bar + per-tile (label bar + image height).
    height = LABEL_H + sum(LABEL_H + img.height for _, img in scaled)
    canvas = Image.new("RGB", (TILE_W, height), "black")
    draw = ImageDraw.Draw(canvas)
    # ImageDraw.text with default bitmap font — no font file dependency:
    # https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html#PIL.ImageDraw.ImageDraw.text
    draw.text((6, 6), caption, fill="white")
    y = LABEL_H
    for label, img in scaled:
        draw.text((6, y + 5), label, fill="white")    # tile label in its bar
        y += LABEL_H
        canvas.paste(img, (0, y))                      # tile below its label
        y += img.height
    return canvas

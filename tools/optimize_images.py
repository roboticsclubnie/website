"""
Generate web-sized derivatives of the site's oversized images.

Originals are never modified or deleted. Each derivative is written alongside
its source with a "-web.jpg" suffix, e.g.

    images/carousel/L1.JPG  ->  images/carousel/L1-web.jpg

Target widths are chosen from how large the image actually renders:

    assets/faculty/*   500px   (drawn as a ~120px circle)
    images/gallery/*  1200px   (gallery tiles cap at ~600 CSS px)
    everything else   1600px   (carousels, CSS background bands, modals)

EXIF orientation is applied before saving so stripping metadata cannot
silently rotate a photo.

Run from the site root:  python tools/optimize_images.py
Add --dry-run to print what would happen without writing anything.
"""

import os
import sys
import glob

from PIL import Image, ImageOps

# Only bother with files above this size; everything smaller is already fine.
MIN_BYTES = 400 * 1024

QUALITY = 82
SUFFIX = "-web.jpg"

WIDTH_RULES = [
    ("assets/faculty/", 500),
    ("images/gallery/", 1200),
]
DEFAULT_WIDTH = 1600


def target_width(relpath):
    normalised = relpath.replace("\\", "/")
    for prefix, width in WIDTH_RULES:
        if normalised.startswith(prefix):
            return width
    return DEFAULT_WIDTH


def candidates():
    found = []
    for pattern in ("images/**/*", "assets/**/*"):
        for path in glob.glob(pattern, recursive=True):
            if not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() not in (".jpg", ".jpeg"):
                continue
            if path.endswith(SUFFIX):
                continue
            if os.path.getsize(path) < MIN_BYTES:
                continue
            found.append(path.replace("\\", "/"))
    return sorted(found)


def main():
    dry_run = "--dry-run" in sys.argv
    before = after = 0
    rows = []

    for src in candidates():
        width = target_width(src)
        dst = os.path.splitext(src)[0] + SUFFIX
        src_bytes = os.path.getsize(src)

        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode != "RGB":
                im = im.convert("RGB")
            if im.width > width:
                height = round(im.height * width / im.width)
                im = im.resize((width, height), Image.LANCZOS)
            out_dim = (im.width, im.height)
            if not dry_run:
                im.save(dst, "JPEG", quality=QUALITY,
                        optimize=True, progressive=True)

        dst_bytes = os.path.getsize(dst) if os.path.exists(dst) else 0
        before += src_bytes
        after += dst_bytes
        rows.append((src, dst, src_bytes, dst_bytes, out_dim))

    for src, dst, sb, db, dim in rows:
        print("%-40s %7.2f MB -> %6.0f KB  %dx%d" %
              (src, sb / 1048576, db / 1024, dim[0], dim[1]))

    print("\n%d files: %.1f MB -> %.1f MB (%.1f%% smaller)" % (
        len(rows), before / 1048576, after / 1048576,
        (1 - after / before) * 100 if before else 0))


if __name__ == "__main__":
    main()

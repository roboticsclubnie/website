"""Emit tools/image-map.txt: original -> web derivative, with real dimensions.

The page-fix agents read this instead of guessing width/height attributes.
"""

import glob
import os

from PIL import Image

SUFFIX = "-web.jpg"
EXTS = (".JPG", ".jpg", ".jpeg", ".JPEG", ".png", ".PNG")


def main():
    rows = []
    seen = set()
    for pattern in ("images/**/*" + SUFFIX, "assets/**/*" + SUFFIX):
        for web in glob.glob(pattern, recursive=True):
            web = web.replace(os.sep, "/")
            if web in seen:
                continue
            seen.add(web)
            stem = web[: -len(SUFFIX)]
            orig = None
            for ext in EXTS:
                if os.path.exists(stem + ext):
                    orig = (stem + ext).replace(os.sep, "/")
                    break
            if orig is None:
                continue
            with Image.open(web) as im:
                dim = (im.width, im.height)
            rows.append((orig, web, dim[0], dim[1],
                         os.path.getsize(orig), os.path.getsize(web)))

    rows.sort()

    with open("tools/image-map.txt", "w", encoding="utf-8") as out:
        out.write("# Web-sized derivatives. Every original is kept on disk, untouched.\n")
        out.write("# Point each <img src> at the WEB path and set width/height to the\n")
        out.write("# values below so the browser can reserve space before the image loads.\n")
        out.write("#\n")
        out.write("# ORIGINAL | WEB | WIDTH | HEIGHT\n")
        for orig, web, w, h, _, _ in rows:
            out.write("%s | %s | %d | %d\n" % (orig, web, w, h))

    orig_bytes = sum(r[4] for r in rows)
    web_bytes = sum(r[5] for r in rows)
    print("%d mappings -> tools/image-map.txt" % len(rows))
    print("originals %.1f MB, derivatives %.1f MB" % (
        orig_bytes / 1048576, web_bytes / 1048576))


if __name__ == "__main__":
    main()

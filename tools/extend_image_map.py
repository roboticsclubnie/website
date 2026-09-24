"""Extend tools/image-map.txt to cover the six secondary pages.

The first pass only covered the images index.html and rikishi.html use. These
pages were still serving originals -- Project.html alone pulled about 105 MB of
camera JPEGs for twelve thumbnails.

Two rules decide what happens to each image:

  resize     wider than MAX_WIDTH, or heavier than SIZE_LIMIT. A capped,
             re-encoded, EXIF-stripped "-web.jpg" derivative is written next to
             the original. Originals are never modified or deleted.
  passthrough  already small enough. The map points the image at itself, so it
             keeps its own src but still gains width/height/alt/loading when
             tools/rewire_images.py rewrites the tag. Reserving the right box
             before the bytes land is what stops the gallery jumping as it loads.

Filename case is taken from the real directory listing, not from the reference in
the HTML. Windows resolves `core.JPG` and `core.jpg` to the same file, so the
existing map had picked up the wrong case for two entries; on GitHub Pages, which
is Linux, the wrong case is a 404. (Those stale keys are rewritten here.)

Derivative names are collision-checked: images/gallery holds both `core.jpg` and
`core.jpeg` -- two genuinely different photographs -- and naive stem+"-web.jpg"
would have had the second silently overwrite the first.
"""

import glob
import io
import os
import re

from PIL import Image, ImageOps

MAX_WIDTH = 1600
SIZE_LIMIT = 250 * 1024
QUALITY = 82
MAP_PATH = "tools/image-map.txt"

PAGES = ["Accommodations.html", "Project.html", "alumni.html",
         "competition.html", "registration.html", "workshop.html"]

IMG_SRC_RE = re.compile(r'<img\b[^>]*?src\s*=\s*"([^"]+)"', re.IGNORECASE)
# Left alone: tiny UI chrome that already carries explicit dimensions.
EXCLUDE = {"images/Logo.png", "images/ham_menu.png"}


def real_path(ref):
    """Resolve a reference to its true on-disk spelling, or None."""
    target = ref.replace("/", os.sep)
    directory, name = os.path.split(target)
    try:
        names = os.listdir(directory if directory else ".")
    except OSError:
        return None
    if name in names:
        return ref
    hit = [n for n in names if n.lower() == name.lower()]
    if not hit:
        return None
    return (directory.replace(os.sep, "/") + "/" + hit[0]) if directory else hit[0]


def load_map():
    entries = {}
    if not os.path.exists(MAP_PATH):
        return entries
    with io.open(MAP_PATH, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or "|" not in line:
                continue
            orig, web, w, h = [p.strip() for p in line.split("|")]
            entries[orig] = (web, int(w), int(h))
    return entries


def derivative_name(orig, taken):
    base, ext = os.path.splitext(orig)
    candidate = base + "-web.jpg"
    if candidate not in taken:
        return candidate
    # e.g. core.jpg -> core-web.jpg, then core.jpeg -> core-jpeg-web.jpg
    return base + "-" + ext.lstrip(".").lower() + "-web.jpg"


def main():
    entries = load_map()

    # Repair keys whose case does not match the disk.
    for key in list(entries):
        fixed = real_path(key)
        if fixed and fixed != key:
            entries[fixed] = entries.pop(key)
            print("map key case fixed: %s -> %s" % (key, fixed))

    wanted = []
    for page in PAGES:
        with io.open(page, encoding="utf-8", newline="") as fh:
            text = fh.read()
        for ref in IMG_SRC_RE.findall(text):
            if ref in EXCLUDE or ref.startswith(("http", "data:")):
                continue
            if ref.endswith("-web.jpg"):
                continue
            if ref not in wanted:
                wanted.append(ref)

    taken = set(v[0] for v in entries.values())
    made = kept = 0
    saved_before = saved_after = 0

    for ref in wanted:
        disk = real_path(ref)
        if disk is None:
            print("!! not on disk, skipped: %s" % ref)
            continue
        if disk in entries:
            continue

        raw = os.path.getsize(disk)
        with Image.open(disk) as im:
            im = ImageOps.exif_transpose(im)
            width, height = im.size
            needs = width > MAX_WIDTH or raw > SIZE_LIMIT

            if needs:
                out = derivative_name(disk, taken)
                taken.add(out)
                if width > MAX_WIDTH:
                    height = int(round(height * MAX_WIDTH / float(width)))
                    width = MAX_WIDTH
                    im = im.resize((width, height), Image.LANCZOS)
                im.convert("RGB").save(out, "JPEG", quality=QUALITY,
                                       optimize=True, progressive=True)
                entries[disk] = (out, width, height)
                saved_before += raw
                saved_after += os.path.getsize(out)
                made += 1
                print("resized  %-42s -> %-42s %dx%d  %dKB -> %dKB"
                      % (disk, out, width, height,
                         raw // 1024, os.path.getsize(out) // 1024))
            else:
                entries[disk] = (disk, width, height)
                kept += 1
                print("kept     %-42s %dx%d  %dKB (already small)"
                      % (disk, width, height, raw // 1024))

    header = ("# original | web | width | height\n"
              "# Generated by tools/write_image_map.py and extended by\n"
              "# tools/extend_image_map.py. When web == original the image was\n"
              "# already small enough to ship as-is; the width/height are still\n"
              "# recorded so the <img> tag can reserve its space.\n")
    with io.open(MAP_PATH, "w", encoding="utf-8") as fh:
        fh.write(header)
        for orig in sorted(entries):
            web, w, h = entries[orig]
            fh.write("%s | %s | %d | %d\n" % (orig, web, w, h))

    print("\n%d derivatives written, %d passed through, %d entries total"
          % (made, kept, len(entries)))
    if saved_before:
        print("resized set: %.1f MB -> %.1f MB"
              % (saved_before / 1048576.0, saved_after / 1048576.0))


if __name__ == "__main__":
    main()

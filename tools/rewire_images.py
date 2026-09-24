"""Repoint <img> tags at the resized derivatives, with real alt text and dimensions.

Three things happen to every matched tag:

  src     swapped to the "-web.jpg" derivative from tools/image-map.txt
  width   } added from the derivative's real pixel size, so the browser can
  height  } reserve the space before the bytes arrive (no layout shift)
  alt     filled in from the table below -- every one of these images shipped
          with alt="" , which tells a screen reader the image is decorative and
          can be skipped. These are the actual content of the gallery.

`loading="lazy"` is kept where present and added where missing, except on images
listed in EAGER (above the fold -- lazy-loading those delays the largest
contentful paint rather than helping it).
"""

import io
import re
import sys

# src (original path) -> alt text
ALT = {
    "assets/expo/robo1.JPG":
        "A talking robot built by the club, on display at the Robo-Expo",
    "assets/expo/IMG_6107.JPG":
        "A gesture-controlled robot demonstrated at the Robo-Expo",
    "assets/expo/robo2.JPG":
        "A six-legged spider robot on display at the Robo-Expo",
    "assets/line/robo3.JPG":
        "A line follower robot tracking the printed course in the arena",
    "assets/line/L1.JPG":
        "Line follower robots lined up at the start of the track",
    "assets/race/IMG_6328.JPG":
        "A Death Race robot crossing the bumpy-terrain section of the course",
    "assets/race/IMG_6356.JPG":
        "A Death Race robot climbing the rocky-terrain section of the course",
    "assets/race/IMG_9828.JPG":
        "The club's own race robot on the Death Race course",
    "assets/war/IMG_6376.JPG":
        "Two robots facing off at the start of a Robo War bout",
    "assets/war/IMG_6377.JPG":
        "Smoke rising from a robot during a Robo War bout",
    "assets/war/IMG_6401.JPG":
        "A war robot lined up and ready to charge its opponent",
    "assets/war/IMG_9859.JPG":
        "A heavily armoured war robot built by the club",
    # Project.html
    "assets/core/IMG_20220709_174406547.jpg":
        "Robotics Club NIE core team members with their projects",
    "assets/core/IMG_20220709_174450365.jpg":
        "Robotics Club NIE core team members at a project showcase",
    # competition.html -- the gallery has no captions, so the alt carries the
    # whole description.
    "assets/competition/competition1.jpeg":
        "Two club members holding up the off-road robots they built for the competition",
    "assets/competition/competition2.jpg":
        "The outdoor competition course laid out with tyres, cones and arches, with participants around it",
    "assets/competition/competition3.jpg":
        "Participants and organisers crouched around a robot in the arena between rounds",
    # alumni.html -- each photo already has a visible label beneath it, so the
    # alt describes the picture instead of repeating the label.
    "images/gallery/alumni.JPG":
        "Three alumni in Robotics Club hoodies at the reunion, in front of the Roborikishi sponsors banner",
    "images/gallery/alumni1.JPG":
        "Two club members and a guest crouched behind a robot at the alumni meet",
    "images/gallery/core.jpg":
        "The Robotics Club core team, around twenty members in club hoodies, in the college hall",
    "images/gallery/core.jpeg":
        "The 2025 core team seated on the steps outside the electronics block",
    # workshop.html -- these all read alt="workshop & events N", which describes
    # nothing and put a raw & in an attribute.
    "assets/workshop/we1.jpg":
        "Students clustered around laptops and a robot during a hands-on workshop session",
    "assets/workshop/we2.jpg":
        "A full classroom of students at a Robotics Club workshop",
    "assets/workshop/we3.jpg":
        "Club members at their exhibition stall, with robots on display in front of the banner",
    "assets/workshop/we4.jpg":
        "A large group of workshop participants with the robots they built",
    "assets/workshop/we5.jpg":
        "Students demonstrating a line-following track to visitors at an exhibition",
    "assets/workshop/we6.jpg":
        "Club members demonstrating a robotic arm and its controller to a visitor",
    "assets/workshop/we7.jpeg":
        "A lecture hall full of students during a Robotics Club talk",
    "assets/workshop/we8.jpeg":
        "School students and club volunteers with a certificate after an outreach workshop",
    "assets/workshop/we9.jpeg":
        "Club members and guests in front of the department banner at an event",
    # Accommodations.html -- both boys' photos shared one alt, and both girls'
    # sets shared another, so a screen reader heard the same sentence repeatedly.
    "assets/Accom/Boys_accom_1.jpeg":
        "A room in the boys' PG accommodation, with a bed and tiled flooring",
    "assets/Accom/Boys_accom_2.jpeg":
        "A second room in the boys' PG accommodation, with a made-up bed",
    "assets/Accom/Girls_accom_1.jpeg":
        "A room in the girls' PG accommodation, with cots and storage boxes",
    "assets/Accom/Girls_accom_2.jpeg":
        "A room in the girls' PG accommodation, with cots and wooden shelving",
    "assets/Accom/Girls_accom_3.jpeg":
        "A room in the girls' PG accommodation, with cots beside a curtained window",
}

EAGER = set()

IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
SRC_RE = re.compile(r'src\s*=\s*"([^"]*)"', re.IGNORECASE)


def load_map(path="tools/image-map.txt"):
    mapping = {}
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or "|" not in line:
                continue
            orig, web, w, h = [p.strip() for p in line.split("|")]
            mapping[orig] = (web, int(w), int(h))
    return mapping


def rewrite_tag(tag, mapping, stats):
    match = SRC_RE.search(tag)
    if not match:
        return tag
    src = match.group(1)
    if src not in mapping:
        return tag
    web, width, height = mapping[src]

    attrs = ['src="%s"' % web, 'width="%d"' % width, 'height="%d"' % height]

    alt = ALT.get(src)
    if alt is None:
        # Keep whatever alt the tag already had rather than inventing one.
        existing = re.search(r'alt\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
        alt = existing.group(1) if existing else ""
    attrs.append('alt="%s"' % alt)

    if src not in EAGER:
        attrs.append('loading="lazy"')
    attrs.append('decoding="async"')

    # Preserve any class the original tag carried.
    cls = re.search(r'class\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
    if cls:
        attrs.insert(1, 'class="%s"' % cls.group(1))

    stats.append(src)
    return "<img " + " ".join(attrs) + ">"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/rewire_images.py <file.html> ...")

    mapping = load_map()
    for path in sys.argv[1:]:
        with io.open(path, encoding="utf-8", newline="") as fh:
            original = fh.read()
        stats = []
        text = IMG_RE.sub(lambda m: rewrite_tag(m.group(0), mapping, stats),
                          original)
        if text != original:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        print("%s: %d img tags repointed" % (path, len(stats)))
        missing = sorted(set(s for s in stats if s not in ALT))
        if missing:
            print("   (kept existing alt for: %s)" % ", ".join(missing))


if __name__ == "__main__":
    main()

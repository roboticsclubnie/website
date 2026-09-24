"""Remove the accidentally duplicated second half of rikishi.css.

rikishi.css was 2017 lines, of which roughly the last 880 were a second copy of
sections that already appear earlier in the file (BODY, NAVBAR, About, Waivy,
Parallax, Gallery, Gallery item hover, Social Links, JS CLASSES). Because the
later copy wins the cascade, the duplicate was not merely dead weight -- it was
silently overriding the first copy.

The duplicate is identified by the second occurrence of the BODY banner, and the
script refuses to touch the file unless what it is about to delete really does
look like that duplicate.
"""

import io
import os

PATH = "rikishi.css"
SEAM = "/* BODY */\nbody {\n\tmargin: 0px;\n"
# Sections that must appear in the tail for it to be the duplicate we expect.
EXPECTED_IN_TAIL = [
    "NAVBAR", "About", "Waivy", "Parallax", "Gallery",
    "Social Links", "JS CLASSES",
]


def main():
    with io.open(PATH, encoding="utf-8", newline="") as fh:
        text = fh.read()

    first = text.find(SEAM)
    if first == -1:
        raise SystemExit("BODY banner not found; aborting without changes.")
    second = text.find(SEAM, first + 1)
    if second == -1:
        raise SystemExit("No second BODY banner: already de-duplicated.")
    if text.find(SEAM, second + 1) != -1:
        raise SystemExit("More than two BODY banners; aborting for a human.")

    # Walk back over the banner comment line(s) that introduce the duplicate.
    cut = text.rfind("\n/****", 0, second)
    if cut == -1 or second - cut > 200:
        cut = second
    else:
        cut += 1  # keep the newline that ends the previous rule

    head, tail = text[:cut], text[cut:]

    missing = [s for s in EXPECTED_IN_TAIL if s not in tail]
    if missing:
        raise SystemExit(
            "Tail does not look like the duplicate (missing %s); aborting."
            % ", ".join(missing))

    # Every selector in the tail must already exist in the head, otherwise we
    # would be deleting rules that appear nowhere else.
    def selectors(chunk):
        found = set()
        for line in chunk.splitlines():
            line = line.strip()
            if line.endswith("{") and not line.startswith(("@", "/*", "*")):
                found.add(line[:-1].strip())
        return found

    only_in_tail = selectors(tail) - selectors(head)
    if only_in_tail:
        raise SystemExit(
            "These selectors exist ONLY in the tail, refusing to delete:\n  "
            + "\n  ".join(sorted(only_in_tail)))

    head = head.rstrip() + "\n"
    with io.open(PATH, "w", encoding="utf-8", newline="") as fh:
        fh.write(head)

    print("rikishi.css: %d lines -> %d lines (removed %d duplicated lines)" % (
        text.count("\n") + 1, head.count("\n") + 1,
        text.count("\n") - head.count("\n")))
    print("bytes: %d -> %d" % (len(text.encode("utf-8")),
                               len(head.encode("utf-8"))))


if __name__ == "__main__":
    main()

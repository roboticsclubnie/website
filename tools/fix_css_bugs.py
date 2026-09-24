"""Site-wide stylesheet corrections that are the same fix in several files.

font-style: bold
    `font-style` accepts normal | italic | oblique -- there is no `bold`, so the
    whole declaration was invalid and dropped, and the blockquote it was meant
    to embolden has been rendering at normal weight. Corrected to font-weight.
    NOTE: this makes those blockquotes visibly bold for the first time.

width: 100vw
    100vw is the viewport width *including* the scrollbar gutter, so on any page
    tall enough to scroll these elements were ~15px wider than the space
    available and pushed out a horizontal scrollbar. Every occurrence here is a
    block whose containing block is already the full available width, so 100%
    is both correct and immune to the scrollbar.

.custom-modal
    Same 100vw problem, but on a fixed overlay. Pinning all four edges is the
    robust spelling.
"""

import glob
import io
import re

FONT_STYLE_RE = re.compile(r"font-style:\s*bold\s*;")

MODAL_OLD = """	left: 0;
	top: 0;
	width: 100vw;
	height: 100vh;
"""
MODAL_NEW = """	/* Pinning all four edges instead of `width: 100vw; height: 100vh` -- 100vw
	   counts the scrollbar gutter, so the overlay was a few pixels wider than
	   the space available and grew its own horizontal scrollbar. */
	left: 0;
	top: 0;
	right: 0;
	bottom: 0;
"""


def main():
    for path in sorted(glob.glob("*.css")):
        if path == "theme.css":
            continue  # only mentions 100vw inside a comment
        with io.open(path, encoding="utf-8", newline="") as fh:
            original = fh.read()
        text = original
        notes = []

        text, n = FONT_STYLE_RE.subn("font-weight: bold;", text)
        if n:
            notes.append("font-style: bold -> font-weight: bold (x%d)" % n)

        if MODAL_OLD in text:
            text = text.replace(MODAL_OLD, MODAL_NEW)
            notes.append(".custom-modal: 100vw/100vh -> inset 0")

        n = len(re.findall(r"width:\s*100vw\s*;", text))
        if n:
            text = re.sub(r"width:\s*100vw\s*;", "width: 100%;", text)
            notes.append("width: 100vw -> 100%% (x%d)" % n)

        if text != original:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            print(path)
            for note in notes:
                print("   " + note)


if __name__ == "__main__":
    main()

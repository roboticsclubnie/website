"""Nav consistency across the eight pages.

"Project" vs "Projects"
    Project.html and competition.html labelled the nav item "Project"; index.html,
    alumni.html, workshop.html and Accommodations.html all labelled the same link
    "Projects", and the page's own <h1> says "Projects". Two pages disagreed with
    the other four and with the page they pointed at.

aria-current="page"
    Only index.html marked which nav item was the current page. Without it a
    screen-reader user tabbing the nav gets no signal that one of these links is
    the page they are already on. Purely semantic -- nothing visual changes,
    because no stylesheet targets [aria-current].
"""

import glob
import io
import re

LABELS = [(">Project<", ">Projects<")]


def main():
    for path in sorted(glob.glob("*.html")):
        with io.open(path, encoding="utf-8", newline="") as fh:
            original = fh.read()
        text = original
        notes = []

        for old, new in LABELS:
            n = text.count(old)
            if n:
                text = text.replace(old, new)
                notes.append('nav label "%s" -> "%s" (x%d)'
                             % (old[1:-1], new[1:-1], n))

        # Mark this page's own nav link as the current page.
        self_link = 'href="%s"' % path
        if self_link in text and 'aria-current' not in text:
            text = text.replace(self_link, self_link + ' aria-current="page"', 1)
            notes.append('aria-current="page" on the %s nav item' % path)

        if text != original:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            print(path)
            for note in notes:
                print("   " + note)


if __name__ == "__main__":
    main()

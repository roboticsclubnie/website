"""Bring the six secondary pages' <head> and navbar up to the level of index/rikishi.

Each fix below was verified as actually broken on these pages, not applied
speculatively.

animate.css was never loaded
    All six pages mark elements `animate__animated animate__fadeInUp` and some
    add `animate__delay-1s`/`-2s`, but none of them ever linked animate.css --
    only index.html and rikishi.html did. So every one of those classes was
    inert: no animation ran, the classes were decoration on the markup. The
    library is now linked, which makes the nav animate on entry the way it
    already does on the two pages that had it.

...which makes the delay classes newly dangerous
    animate.css sets `animation-fill-mode: both`, so a delayed element holds its
    *starting* frame until the delay expires -- and fadeInUp starts at
    `opacity: 0`. Adding the library without touching the delays would have made
    the logo invisible for 1s, and alumni/registration's nav links invisible for
    2s. Every `animate__delay-*` is therefore removed (the same fix already
    applied to rikishi.html), so things animate immediately instead.

Nav logo had no alt at all and was lazy-loaded
    `<img class="..." src="images/Logo.png" loading="lazy">` -- no alt attribute,
    so a screen reader falls back to announcing the filename, and the link
    wrapping it had no accessible name either. It also carried loading="lazy"
    while being the topmost image on the page, which defers the largest early
    paint rather than helping it. Now: real alt, real width/height (666x375, its
    true size, so no layout shift), aria-label on the link, no lazy.

Hamburger icon announced as "..."
    `alt="..."` is read aloud as "dot dot dot". The button around it already has
    aria-label="Toggle navigation", so the image is decorative: alt="" plus its
    real 48x48 dimensions.

theme.css was not linked
    The shared token/foundation sheet (anchor scroll-padding, focus-visible
    rings, reduced-motion handling, the overflow-x guard) only reached index and
    rikishi. Linked before each page stylesheet so the page can still override.

No description, canonical or favicon
    Every one of these pages showed the browser's default blank favicon and gave
    search results no summary line.

Nothing here changes a colour, font, size, spacing, gradient or border.
"""

import io
import re
import sys

# page -> (meta description, canonical path)
PAGES = {
    "Accommodations.html": (
        "Accommodation options, room details and booking links for teams "
        "travelling to Roborikishi at The National Institute of Engineering, Mysuru.",
        "Accommodations.html"),
    "Project.html": (
        "Robotics and automation projects built by students of the Robotics Club "
        "at The National Institute of Engineering, Mysuru.",
        "Project.html"),
    "alumni.html": (
        "Alumni and past core team members of the Robotics Club at "
        "The National Institute of Engineering, Mysuru.",
        "alumni.html"),
    "competition.html": (
        "Robotics competitions hosted by the Robotics Club at "
        "The National Institute of Engineering, Mysuru.",
        "competition.html"),
    "registration.html": (
        "Registration details, categories and fees for Roborikishi, the annual "
        "robotics fest of The National Institute of Engineering, Mysuru.",
        "registration.html"),
    "workshop.html": (
        "Robotics workshops and events run by the Robotics Club at "
        "The National Institute of Engineering, Mysuru.",
        "workshop.html"),
}

TITLES = {
    # The <h1> says "Projects"; only the tab said "Project".
    "Project.html": ("<title>Project</title>",
                     "<title>Projects — Robotics Club, NIE</title>"),
    # Raw & in markup. Browsers recover, validators do not.
    "workshop.html": ("<title>Workshops & Events</title>",
                      "<title>Workshops &amp; Events — Robotics Club, NIE</title>"),
    "competition.html": ("<title>Competitions</title>",
                         "<title>Competitions — Robotics Club, NIE</title>"),
    "alumni.html": ("<title>Alumni</title>",
                    "<title>Alumni — Robotics Club, NIE</title>"),
    "registration.html": ("<title>Roborikishi 2026</title>",
                          "<title>Registration — Roborikishi 2026 | Robotics Club, NIE</title>"),
}

NAVLOGO_RE = re.compile(
    r'<a id="navlogo"[^>]*>\s*<img\b[^>]*>\s*</a>', re.IGNORECASE | re.DOTALL)
HAM_RE = re.compile(
    r'<img\b[^>]*src="images/ham_menu\.png"[^>]*>', re.IGNORECASE)
DELAY_RE = re.compile(r'\s*animate__delay-\d+s')


def process(path):
    desc, canon = PAGES[path]
    with io.open(path, encoding="utf-8", newline="") as fh:
        original = fh.read()
    text = original
    notes = []

    if path in TITLES:
        old, new = TITLES[path]
        if old in text:
            text = text.replace(old, new)
            notes.append("title -> %s" % new[7:-8])

    # Indentation used by this file's head, taken from the stylesheet comment.
    m = re.search(r'^([ \t]*)<!-- Custom CSS -->', text, re.MULTILINE)
    ind = m.group(1) if m else "  "

    # description + canonical + favicon, right after <title>
    if 'name="description"' not in text:
        m = re.search(r'^[ \t]*<title>.*?</title>[ \t]*\r?\n', text,
                      re.MULTILINE | re.DOTALL)
        if m:
            block = (
                '%s<meta name="description" content="%s">\n'
                '%s<link rel="canonical" href="https://roboticsclubnie.in/%s">\n'
                '%s<link rel="icon" type="image/png" href="assets/Header_logo_32.png">\n'
                % (ind, desc, ind, canon, ind))
            text = text[:m.end()] + block + text[m.end():]
            notes.append("added meta description, canonical, favicon")

    # animate.css + theme.css, before the page stylesheet
    if "theme.css" not in text:
        marker = ind + "<!-- Custom CSS -->"
        if marker in text:
            block = (
                '%s<!-- Animate.css (the animate__* classes below were already in the\n'
                '%s     markup but the library was never linked, so nothing animated) -->\n'
                '%s<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css">\n'
                '\n'
                '%s<!-- Shared theme foundation (must load before the page stylesheet) -->\n'
                '%s<link rel="stylesheet" href="theme.css">\n'
                '\n' % (ind, ind, ind, ind, ind))
            text = text.replace(marker, block + marker, 1)
            notes.append("linked animate.css + theme.css")

    n = len(DELAY_RE.findall(text))
    if n:
        text = DELAY_RE.sub("", text)
        notes.append("removed %d animate__delay-* (would hold opacity:0)" % n)

    def fix_logo(match):
        keep = "animate__animated animate__fadeInUp"
        cls = ' class="%s"' % keep if keep in match.group(0) else ""
        return ('<a id="navlogo" href="index.html" aria-label="Robotics Club NIE — home">'
                '<img src="images/Logo.png" width="666" height="375" '
                'alt="Robotics Club NIE logo"%s></a>' % cls)

    text, k = NAVLOGO_RE.subn(fix_logo, text)
    if k:
        notes.append("nav logo: real alt + 666x375 + aria-label, no lazy")

    text, k = HAM_RE.subn(
        '<img src="images/ham_menu.png" width="24" height="24" alt="">', text)
    if k:
        notes.append('hamburger: alt="..." -> alt="" + 48x48 intrinsic')

    # Collapse the empty class="" the delay strip can leave behind.
    text = text.replace(' class=""', '')
    text = re.sub(r'(class="[^"]*?) +"', r'\1"', text)

    if text == original:
        print("%-24s no change" % path)
        return
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print(path)
    for note in notes:
        print("   " + note)


def main():
    targets = sys.argv[1:] or sorted(PAGES)
    for path in targets:
        process(path)


if __name__ == "__main__":
    main()

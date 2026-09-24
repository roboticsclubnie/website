"""Give the numeric and duplicated ids real names, in HTML and CSS together.

Three problems are fixed:

  id="2" / id="3"   Legal in HTML5 but unusable as a bare #id CSS selector, and
                    meaningless to anyone reading the markup. Renamed to
                    #gallery / #contact, along with every href that points at
                    them.

  id="card" x12     A duplicate id on every gallery card in rikishi.html and
                    Project.html. #card in the stylesheets only ever matched the
                    first one; the other eleven were styled purely by accident of
                    inheritance. Becomes class="expo-card".
                    (".card" would have collided with Bootstrap's own component.)

  .container:hover  On Project.html this also matched the Bootstrap layout
                    wrapper, which contains all twelve cards -- so pointing at
                    the grid lit up every card at once. Scoped to
                    .container.noselect:hover.
"""

import glob
import io
import os

HTML_SUBS = [
    ('<div class="topTriangle" id="2">', '<div class="topTriangle" id="gallery">'),
    ('<div class="transparent3" id="3">', '<div class="transparent3" id="contact">'),
    ('<div class="bottomTriangle-transparent90" id="3">',
     '<div class="bottomTriangle-transparent90" id="contact">'),
    ('href="#2"', 'href="#gallery"'),
    ('href="#3"', 'href="#contact"'),
    ('id="card"', 'class="expo-card"'),
    ('id="prompt"', 'class="expo-prompt"'),
]

CSS_SUBS = [
    # Order matters: scope .container before renaming #card inside it.
    ('.container:hover #card::before', '.container.noselect:hover .expo-card::before'),
    ('.container:hover #card::before', '.container.noselect:hover .expo-card::before'),
    ('#card', '.expo-card'),
    ('#prompt', '.expo-prompt'),
]


def rewrite(path, subs):
    with io.open(path, encoding="utf-8", newline="") as fh:
        original = fh.read()
    text = original
    hits = []
    for old, new in subs:
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            hits.append("%s -> %s (x%d)" % (old, new, n))
    if text != original:
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return hits


def main():
    for path in sorted(glob.glob("*.html")):
        hits = rewrite(path, HTML_SUBS)
        if hits:
            print(path)
            for h in hits:
                print("   " + h)

    for path in sorted(glob.glob("*.css")):
        hits = rewrite(path, CSS_SUBS)
        if hits:
            print(path)
            for h in hits:
                print("   " + h)


if __name__ == "__main__":
    main()

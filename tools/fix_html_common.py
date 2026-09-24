"""Site-wide HTML corrections that repeat across pages.

mailto: with a leading space
    `href="mailto: support@..."` -- the space after the colon is part of the URL,
    so the address handed to the mail client began with a space. Some clients
    cope, others refuse the address outright.

External links without rel="noopener"
    A target="_blank" link gives the opened page a window.opener handle back to
    this one unless rel="noopener" is set. Modern browsers imply it, older ones
    do not; stating it costs nothing.
    (These links also had no target at all, so they replaced the site in the
    same tab -- now they open alongside it, which is the usual expectation for
    an off-site social link.)

Content typos
    Two headings on rikishi.html.

jQuery
    rikishi.js no longer uses it and neither page has any other jQuery, so the
    tag was 30 KB of unused download.
"""

import glob
import io

SITE_WIDE = [
    ('href="mailto: support@roboticsclubnie.in"',
     'href="mailto:support@roboticsclubnie.in"'),
    ('<a href="https://instagram.com/roboticsclub_nie">',
     '<a href="https://instagram.com/roboticsclub_nie" target="_blank" rel="noopener">'),
    ('<a href="https://github.com/roboticsclub-nie">',
     '<a href="https://github.com/roboticsclub-nie" target="_blank" rel="noopener">'),
]

PER_FILE = {
    "rikishi.html": [
        ("<h2>Deth Race - Bumpy terrain</h2>",
         "<h2>Death Race — Bumpy terrain</h2>"),
        ("<h2>Death Race - Rocky terrain</h2>",
         "<h2>Death Race — Rocky terrain</h2>"),
        ("<h2>Lets get fighting!</h2>", "<h2>Let's get fighting!</h2>"),
        ('  <!-- Jquery -->\n  <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>\n\n', ""),
    ],
}


def main():
    for path in sorted(glob.glob("*.html")):
        with io.open(path, encoding="utf-8", newline="") as fh:
            original = fh.read()
        text = original
        notes = []

        for old, new in SITE_WIDE + PER_FILE.get(path, []):
            n = text.count(old)
            if n:
                text = text.replace(old, new)
                label = old if len(old) < 60 else old[:57] + "..."
                notes.append("%s (x%d)" % (label, n))

        if text != original:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            print(path)
            for note in notes:
                print("   " + note)


if __name__ == "__main__":
    main()

"""Make each page actually request the fonts its stylesheet uses.

Oswald never loaded on six pages
    Accommodations.css, Alumni.css, competition.css, workshop.css, project.css and
    registration.css all set `font-family: 'Oswald', sans-serif` on the social
    footer, but every one of those pages requested only Space Grotesk. A
    font-family the page never downloads falls through to the next name in the
    list, so that footer has been rendering in the browser's default sans-serif
    -- not in the typeface the stylesheet asks for. index.html and rikishi.html
    requested Oswald and rendered it correctly, which is why the same footer
    looked different depending on the page.

registration.html requested no fonts at all
    It had no Google Fonts link. Its stylesheet asks for Space Grotesk and Oswald,
    so the whole page was falling back to a system sans-serif while its siblings
    used Space Grotesk. It also has the only @font-face in the site ('Major
    Snafu', a local .ttf) which was unaffected.

preconnect
    The two hosts are added as preconnect hints, matching what index.html and
    rikishi.html already do. The stylesheet request goes to fonts.googleapis.com
    but the font files come from fonts.gstatic.com, and the browser cannot know
    about the second host until it has parsed the first response.

This changes which weights are available, not which typeface any rule asks for --
no font-family declaration is edited.
"""

import io
import re

# Weights taken from the requests index.html and rikishi.html already make, so
# every page ends up asking for the same faces.
FONTS = ("https://fonts.googleapis.com/css2"
         "?family=Oswald:wght@200;400"
         "&family=Space+Grotesk:wght@300;400;500;600;700"
         "&display=swap")

PAGES = ["Accommodations.html", "Project.html", "alumni.html",
         "competition.html", "workshop.html", "registration.html"]

EXISTING_RE = re.compile(
    r'[ \t]*<link[^>]*fonts\.googleapis\.com[^>]*>[ \t]*\r?\n', re.IGNORECASE)


def main():
    for path in PAGES:
        with io.open(path, encoding="utf-8", newline="") as fh:
            original = fh.read()
        text = original
        notes = []

        m = re.search(r'^([ \t]*)<!-- Bootstrap CSS -->', text, re.MULTILINE)
        ind = m.group(1) if m else "  "

        block = (
            '%s<!-- Fonts: Oswald + Space Grotesk in a single request.\n'
            '%s     The page stylesheet uses both, but only Space Grotesk was\n'
            '%s     requested, so every Oswald rule fell back to sans-serif. -->\n'
            '%s<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '%s<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '%s<link href="%s" rel="stylesheet">\n'
            % (ind, ind, ind, ind, ind, ind, FONTS))

        text, removed = EXISTING_RE.subn("", text)
        if removed:
            notes.append("replaced %d Space-Grotesk-only font request(s)" % removed)
        else:
            notes.append("added the missing font request (page had none)")

        # Drop the now-empty "Google Fonts" comment the old link sat under.
        text = re.sub(r'[ \t]*<!-- Google Fonts -->[ \t]*\r?\n\s*(?=</head>)',
                      "", text)
        text = re.sub(r'[ \t]*<!-- Google Fonts -->[ \t]*\r?\n', "", text)

        marker = ind + "<!-- Bootstrap CSS -->"
        if marker in text:
            text = text.replace(marker, block + "\n" + marker, 1)
            notes.append("preconnect + Oswald 200/400 + Space Grotesk 300-700")
        else:
            print("%-24s !! no Bootstrap CSS marker, skipped" % path)
            continue

        if text == original:
            print("%-24s no change" % path)
            continue
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        print(path)
        for note in notes:
            print("   " + note)


if __name__ == "__main__":
    main()

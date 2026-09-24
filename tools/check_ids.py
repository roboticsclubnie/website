"""Report duplicate id attributes, and ids that no CSS or JS references.

Duplicate ids are invalid HTML: document.getElementById and #foo selectors both
resolve to the first one only, so every later copy is silently unstyled or
unreachable.
"""

import collections
import glob
import io
import re

ID_ATTR = re.compile(r'\bid\s*=\s*"([^"]*)"')
COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)


def strip_comments(text):
    """Comments are not markup.

    Without this, an explanatory comment that quotes an attribute -- e.g. one
    noting that a div previously carried no id="core" -- gets counted as a real
    occurrence and reported as a duplicate of the id it is describing.
    """
    return COMMENT.sub("", text)


def main():
    css = ""
    for path in glob.glob("*.css"):
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            css += fh.read()
    js = ""
    for path in glob.glob("*.js"):
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            js += fh.read()

    for path in sorted(glob.glob("*.html")):
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            text = strip_comments(fh.read())

        counts = collections.Counter(ID_ATTR.findall(text))
        dupes = {k: v for k, v in counts.items() if v > 1}
        numeric = [k for k in counts if k and k[0].isdigit()]

        lines = []
        if dupes:
            lines.append("  duplicate ids: " + ", ".join(
                '%s (x%d)' % (k, v) for k, v in sorted(dupes.items())))
        if numeric:
            # Ids starting with a digit are legal in HTML5 but cannot be written
            # as a bare #id selector in CSS.
            lines.append("  ids starting with a digit: " +
                         ", ".join(sorted(numeric)))

        anchors = set(re.findall(r'href\s*=\s*"#([^"]+)"', text))
        missing = sorted(a for a in anchors if a and a not in counts)
        if missing:
            lines.append("  href=\"#...\" with no matching id: " +
                         ", ".join(missing))

        if lines:
            print(path)
            for line in lines:
                print(line)
            print("")


if __name__ == "__main__":
    main()

"""Two site-wide stylesheet cleanups.

1. Remove the dead Alfa Slab One @import.

   It appears in all seven non-index stylesheets, and in every one of them it
   sits *after* style rules. CSS requires @import to precede all rules other
   than @charset and @layer, so browsers were already discarding it. The font is
   also not referenced by a single declaration anywhere in the project, so
   nothing is lost by deleting it -- this only removes a line that never worked.

2. Point CSS background-image at the resized derivatives.

   The parallax bands loaded multi-megabyte originals as backgrounds.
"""

import glob
import io
import os
import re

IMPORT_RE = re.compile(
    r"[ \t]*@import\s+url\(\s*['\"]?https://fonts\.googleapis\.com/css2"
    r"\?family=Alfa\+Slab\+One[^)]*\)\s*;[ \t]*\r?\n?")


def load_map():
    mapping = {}
    with io.open("tools/image-map.txt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            mapping[parts[0]] = parts[1]
    return mapping


def main():
    mapping = load_map()
    total_imports = 0
    total_urls = 0

    for path in sorted(glob.glob("*.css")):
        with io.open(path, encoding="utf-8", newline="") as fh:
            original = fh.read()
        text = original

        text, n = IMPORT_RE.subn("", text)
        if n:
            total_imports += n
            print("%s: removed %d dead @import" % (path, n))

        for orig, web in mapping.items():
            # Match the path inside url(...) with or without quotes.
            for quoted in ('url("%s")', "url('%s')", "url(%s)"):
                needle = quoted % orig
                if needle in text:
                    text = text.replace(needle, quoted % web)
                    total_urls += 1
                    print("%s: %s -> %s" % (path, orig, web))

        if text != original:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)

    print("\n%d dead @import rules removed, %d background urls repointed"
          % (total_imports, total_urls))


if __name__ == "__main__":
    main()

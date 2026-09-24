"""Put every page on the same Bootstrap 5.0.2 build.

Why
---
Seven of the eight pages loaded Bootstrap 4.5.2 while index.html and rikishi.html
loaded 5.0.2, so the same markup behaved differently depending on which page you
were on. Project.html was the extreme case: it loaded BS4's CSS, then jQuery
3.6.0, then BS5's JS bundle, then jQuery 3.5.1 *slim*, then Popper, then BS4's
JS. The last two lines undid the ones above them -- BS4's JS overwrote the BS5
bundle, and slim jQuery overwrote full jQuery -- so the page ended up running BS4
against markup this migration writes as BS5.

What changes
------------
CSS      BS 4.5.2 (maxcdn / stackpath) -> BS 5.0.2 on jsDelivr, with SRI.
JS       the jquery-slim + Popper + BS4 trio -> the single BS5 bundle, with SRI.
         BS5 ships Popper inside the bundle and needs no jQuery, so three
         requests become one. Pages that already had the bundle just lose the
         stale trio.
jQuery   dropped everywhere. rikishi.js was rewritten to vanilla JS and nothing
         else on the site calls `$`, so this was ~30 KB of unused download per
         page. (registration.html pinned Popper 2.5.4 where every other page
         pinned 2.9.3 -- moot now that both are gone.)
attrs    data-toggle -> data-bs-toggle, data-target -> data-bs-target. BS5
         namespaced its data attributes; without this the hamburger menu is
         inert on mobile.

What deliberately does NOT change
---------------------------------
`class="close"` is left alone on all 24 modal close buttons. BS5 renamed *its*
`.close` to `.btn-close`, but these spans are not Bootstrap's -- they hold a
literal "x", they are styled by the site's own `.close` rule in rikishi.css and
project.css, and rikishi.js finds them with `.querySelector(".close")`. Renaming
them would unstyle every close button and break the modals.

No colour, font, size, spacing or border is touched.

Reading is done line by line and matching is done on URL substrings, never on
multi-line literals -- an earlier attempt at this used a `\n`-joined string and
silently matched nothing on the files with CRLF endings. Each line keeps its own
terminator, so mixed endings survive untouched.
"""

import io
import sys

BS5_CSS = ('<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.2/dist/css/bootstrap.min.css" rel="stylesheet"\n'
           '{i}  integrity="sha384-EVSTQN3/azprG1Anm3QDgpJLIm9Nao0Yz1ztcQTwFspd3yD65VohhpuuCOmLASjC"\n'
           '{i}  crossorigin="anonymous">')

BS5_JS = ('<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.0.2/dist/js/bootstrap.bundle.min.js"\n'
          '{i}  integrity="sha384-MrcW6ZMFYlzcLA8Nl+NtUVF0sA7MsXsP1UyJoMp4YLEuNSfAP+JcXn/tWtIaxVXM"\n'
          '{i}  crossorigin="anonymous"></script>')

BS4_CSS_URLS = (
    "bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css",
)
BS4_JS_URLS = (
    "bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js",
)
BS5_JS_URL = "bootstrap@5.0.2/dist/js/bootstrap.bundle.min.js"
DROP_URLS = (
    "code.jquery.com/jquery",
    "@popperjs/core@",
)

ATTRS = [
    ('data-toggle="', 'data-bs-toggle="'),
    ('data-target="', 'data-bs-target="'),
    ('data-dismiss="', 'data-bs-dismiss="'),
    ('data-ride="', 'data-bs-ride="'),
    ('data-slide="', 'data-bs-slide="'),
    ('data-slide-to="', 'data-bs-slide-to="'),
    ('data-parent="', 'data-bs-parent="'),
    ('data-spy="', 'data-bs-spy="'),
]


def indent_of(line):
    return line[:len(line) - len(line.lstrip())]


def split_terminator(line):
    for end in ("\r\n", "\n", "\r"):
        if line.endswith(end):
            return line[:-len(end)], end
    return line, ""


def migrate(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        original = fh.read()

    lines = original.splitlines(True)
    has_bs5_js = any(BS5_JS_URL in ln for ln in lines)

    out = []
    notes = []
    for line in lines:
        body, end = split_terminator(line)
        ind = indent_of(body)

        if any(u in body for u in BS4_CSS_URLS):
            out.append(ind + BS5_CSS.format(i=ind) + end)
            notes.append("CSS -> Bootstrap 5.0.2 + SRI")
            continue

        if any(u in body for u in BS4_JS_URLS):
            if has_bs5_js:
                notes.append("dropped stale Bootstrap 4 JS (bundle already loaded)")
            else:
                out.append(ind + BS5_JS.format(i=ind) + end)
                notes.append("JS -> Bootstrap 5.0.2 bundle + SRI")
            continue

        if any(u in body for u in DROP_URLS):
            what = "jQuery" if "jquery" in body.lower() else "Popper"
            notes.append("dropped " + what + " (unused; BS5 bundles Popper)")
            continue

        out.append(line)

    text = "".join(out)

    # A comment whose scripts we just deleted would otherwise sit there labelling
    # nothing. Only comments that name the thing we removed are candidates, and
    # only when their next real neighbour is another comment or the end of the
    # body. (Restricting it to script-related wording matters: an earlier version
    # keyed purely on "next neighbour is a comment" and ate
    # `<!-- Book Button - Boys -->`, which labelled a live booking button that
    # simply had a second comment under it.)
    SCRIPTY = ("bootstrap", "jquery", "popper", "script")
    lines = text.splitlines(True)
    keep = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith("<!--") and stripped.endswith("-->")
                and any(w in stripped.lower() for w in SCRIPTY)):
            nxt = ""
            for later in lines[idx + 1:]:
                if later.strip():
                    nxt = later.strip()
                    break
            if nxt.startswith("<!--") or nxt.startswith("</body"):
                notes.append("removed now-empty comment " + stripped)
                continue
        keep.append(line)
    text = "".join(keep)

    for old, new in ATTRS:
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            notes.append("%s -> %s (x%d)" % (old.rstrip('="'), new.rstrip('="'), n))

    if text == original:
        print("%-22s no change" % path)
        return
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print(path)
    for note in notes:
        print("   " + note)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/migrate_bootstrap5.py <file.html> ...")
    for path in sys.argv[1:]:
        migrate(path)


if __name__ == "__main__":
    main()

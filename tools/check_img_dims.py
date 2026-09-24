"""Find images whose CSS overrides one dimension but not the other.

Adding width/height attributes to <img> lets the browser reserve the correct box
before the image decodes, which prevents layout shift. But if a CSS rule then
sets only ONE of the two dimensions, the other keeps the raw attribute value in
pixels instead of scaling with it -- and with loading="lazy" the browser has no
decoded image to derive an aspect ratio from, so nothing corrects it.

That is how #QMark became a 56x1284 sliver that stretched .headquote down the
whole page. Any element matched by a rule that sets one dimension needs the
other set to `auto`.

This pairs each <img> that has width/height attributes with the CSS rules whose
selector could match it, and reports rules setting exactly one dimension.
"""

import glob
import io
import os
import re

IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')
COMMENT_HTML = re.compile(r'<!--.*?-->', re.DOTALL)
COMMENT_CSS = re.compile(r'/\*.*?\*/', re.DOTALL)
RULE_RE = re.compile(r'([^{}]+)\{([^{}]*)\}')


def css_rules(paths):
    """(selector, declarations) for every rule, media queries flattened."""
    out = []
    for path in paths:
        text = COMMENT_CSS.sub("", io.open(path, encoding="utf-8", errors="replace").read())
        # flatten one level of @media by removing the wrapper braces
        text = re.sub(r'@media[^{]*\{', "", text)
        for sel, body in RULE_RE.findall(text):
            sel = " ".join(sel.split())
            if not sel or sel.startswith("@"):
                continue
            out.append((path, sel, body))
    return out


def dim_of(body, prop):
    m = re.search(r'(?:^|;)\s*' + prop + r'\s*:\s*([^;]+)', body, re.IGNORECASE)
    return m.group(1).strip() if m else None


def selector_could_match(sel, img_id, img_classes, tag="img"):
    """Conservative: does any comma-branch's LAST compound target this img?"""
    for branch in sel.split(","):
        last = branch.strip().split()[-1] if branch.strip() else ""
        if not last:
            continue
        last = last.split(":")[0]
        ids = re.findall(r'#([\w-]+)', last)
        classes = re.findall(r'\.([\w-]+)', last)
        bare = re.match(r'^([a-zA-Z][\w-]*)', last)
        if ids and img_id not in ids:
            continue
        if classes and not set(classes) <= set(img_classes):
            continue
        if not ids and not classes:
            if not bare or bare.group(1).lower() != tag:
                continue
        yield_ok = True
        if yield_ok:
            return True
    return False


def main():
    stylesheets = sorted(glob.glob("*.css"))
    rules = css_rules(stylesheets)
    problems = []

    for page in sorted(glob.glob("*.html")):
        text = COMMENT_HTML.sub("", io.open(page, encoding="utf-8", errors="replace").read())
        # which stylesheets does this page actually load?
        linked = set(re.findall(r'href\s*=\s*"([^"]+\.css)"', text))
        for tag in IMG_RE.findall(text):
            attrs = dict(ATTR_RE.findall(tag))
            if "width" not in attrs or "height" not in attrs:
                continue
            img_id = attrs.get("id", "")
            img_classes = (attrs.get("class") or "").split()
            for path, sel, body in rules:
                if path not in linked:
                    continue
                w, h = dim_of(body, "width"), dim_of(body, "height")
                if (w is None) == (h is None):
                    continue                      # both or neither -- fine
                if not selector_could_match(sel, img_id, img_classes):
                    continue
                if w and w.lower() in ("auto", "inherit", "unset"):
                    continue
                if h and h.lower() in ("auto", "inherit", "unset"):
                    continue
                which = "width" if w else "height"
                problems.append((page, attrs.get("src", "?"), path, sel,
                                 "%s: %s" % (which, w or h),
                                 "no %s -> attribute %s=%s used verbatim"
                                 % ("height" if w else "width",
                                    "height" if w else "width",
                                    attrs["height"] if w else attrs["width"])))

    if not problems:
        print("No image is sized on one axis only.")
        return
    seen = set()
    print("ONE-AXIS SIZING (%d):" % len(problems))
    for page, src, path, sel, decl, note in problems:
        key = (path, sel, src)
        if key in seen:
            continue
        seen.add(key)
        print("   %-20s %-34s" % (page, os.path.basename(src)[:34]))
        print("       %s  {%s}  -- %s" % (sel[:44], decl, note))


if __name__ == "__main__":
    main()

"""Find references that only resolve because Windows ignores filename case.

The site is developed on Windows and served from GitHub Pages, which runs Linux.
Windows treats `core.jpg` and `core.JPG` as the same file; Linux does not. So a
src that differs from the real filename only in case works perfectly on the
developer's machine and 404s once deployed -- the single most common way a static
site "works locally, broken live".

This walks every href/src in every page, plus every url() in every stylesheet,
resolves it against the real directory listing, and reports:

  MISSING       nothing on disk matches, even case-insensitively -- a hard 404
  CASE          a file matches case-insensitively but not exactly -- 404 on Linux
  ROOT          starts with "/" -- absolute from the server root, so it breaks
                on file:// and on any project-path deploy

CSS url() is resolved relative to the STYLESHEET's own directory, not the page
that links it -- getting this wrong is the other classic silent-404 source.

Query strings and fragments are stripped before checking; absolute URLs, mailto:
and tel: are skipped.
"""

import glob
import io
import os
import re

REF_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.IGNORECASE)
# url(foo)  url('foo')  url("foo")
URL_RE = re.compile(r'url\(\s*(?:"([^"]*)"|\'([^\']*)\'|([^)\'"]*))\s*\)', re.IGNORECASE)
# Commented-out markup and prose that happens to mention a path are not live
# references. Scanning them reports breaks no browser would ever request.
HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
CSS_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
SKIP = ("http://", "https://", "//", "mailto:", "tel:", "data:", "#", "javascript:")


def real_names(directory):
    try:
        return os.listdir(directory if directory else ".")
    except OSError:
        return None


def check(ref, base, source, problems):
    """Resolve one reference and record any problem.

    `base` is the directory the reference is relative to -- "" for HTML in the
    site root, the stylesheet's own directory for CSS url().
    """
    if ref.startswith(SKIP) or not ref.strip():
        return
    if ref.startswith("/"):
        problems.append(("ROOT", source, ref, "absolute from server root"))
        return
    clean = ref.split("#")[0].split("?")[0]
    if not clean:
        return
    clean = clean.replace("%20", " ")
    target = os.path.normpath(os.path.join(base, clean.replace("/", os.sep)))
    if os.path.exists(target):
        # Exists -- but does the case match what is really on disk?
        directory, name = os.path.split(target)
        names = real_names(directory)
        if names is not None and name not in names:
            hit = [n for n in names if n.lower() == name.lower()]
            problems.append(("CASE", source, ref,
                             "on disk it is '%s'" % (hit[0] if hit else "?")))
        return
    directory, name = os.path.split(target)
    names = real_names(directory)
    if names is None:
        problems.append(("MISSING", source, ref, "no such directory"))
        return
    hit = [n for n in names if n.lower() == name.lower()]
    if hit:
        problems.append(("CASE", source, ref, "on disk it is '%s'" % hit[0]))
    else:
        problems.append(("MISSING", source, ref, "not on disk"))


def main():
    problems = []
    for path in sorted(glob.glob("*.html")):
        with io.open(path, encoding="utf-8", newline="") as fh:
            text = HTML_COMMENT_RE.sub("", fh.read())
        for ref in REF_RE.findall(text):
            check(ref, "", path, problems)

    for path in sorted(glob.glob("*.css")):
        with io.open(path, encoding="utf-8", newline="") as fh:
            text = CSS_COMMENT_RE.sub("", fh.read())
        base = os.path.dirname(path)
        for groups in URL_RE.findall(text):
            ref = next((g for g in groups if g), "")
            check(ref, base, path, problems)

    if not problems:
        print("No broken, case-mismatched or root-absolute references.")
        return
    for kind in ("MISSING", "CASE", "ROOT"):
        rows = [p for p in problems if p[0] == kind]
        if not rows:
            continue
        print("%s (%d)" % (kind, len(rows)))
        for _, source, ref, note in rows:
            print("   %-22s %-46s %s" % (source, ref, note))
        print()


if __name__ == "__main__":
    main()

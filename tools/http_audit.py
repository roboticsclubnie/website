"""Fetch every page over HTTP and check every subresource returns 200.

check_links.py resolves references against the filesystem. This does the same
job over the wire against the running dev server, which additionally catches
anything the server itself refuses to serve, and confirms the pages themselves
are reachable at the URLs the nav actually uses.
"""
import glob
import os
import re
import urllib.request
import urllib.error
from urllib.parse import quote, urljoin, urlsplit

BASE = "http://127.0.0.1:5501/"
REF_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.IGNORECASE)
URL_RE = re.compile(r'url\(\s*(?:"([^"]*)"|\'([^\']*)\'|([^)\'"]*))\s*\)', re.IGNORECASE)
COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
SKIP = ("http://", "https://", "//", "mailto:", "tel:", "data:", "#", "javascript:")


def status(url):
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def fetch(url):
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return "ERR:%s" % type(e).__name__, ""


def refs_of(text, is_css):
    if is_css:
        for groups in URL_RE.findall(text):
            ref = next((g for g in groups if g), "")
            if ref:
                yield ref
    else:
        # Commented-out markup is not a live reference. registration.html keeps a
        # disabled registration block whose hrefs hold raw spaces; scanning it
        # reported a break that no browser would ever request.
        for ref in REF_RE.findall(COMMENT_RE.sub("", text)):
            yield ref


seen = {}
bad = []
pages = sorted(glob.glob("*.html"))
print("pages: %d" % len(pages))

for page in pages:
    purl = urljoin(BASE, page)
    st, body = fetch(purl)
    if st != 200:
        bad.append((page, page, st))
        continue
    for ref in refs_of(body, False):
        if ref.startswith(SKIP) or not ref.strip():
            continue
        target = urljoin(purl, ref.split("#")[0])
        if not target.startswith(BASE) or target in seen:
            continue
        s = status(target)
        seen[target] = s
        if s != 200:
            bad.append((page, ref, s))
        # follow stylesheets one level for url()
        if urlsplit(target).path.endswith(".css") and s == 200:
            cst, cbody = fetch(target)
            for curl in refs_of(cbody, True):
                if curl.startswith(SKIP) or not curl.strip():
                    continue
                ct = urljoin(target, curl.split("#")[0])
                if not ct.startswith(BASE) or ct in seen:
                    continue
                cs = status(ct)
                seen[ct] = cs
                if cs != 200:
                    bad.append((os.path.basename(target), curl, cs))

print("unique URLs checked: %d" % len(seen))
if bad:
    print("\nNON-200 (%d):" % len(bad))
    for src, ref, s in bad:
        print("   %-24s %-52s %s" % (src, ref[:52], s))
else:
    print("all subresources returned 200")

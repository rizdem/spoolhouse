"""
updates.py - tells you when a newer Spoolhouse is out.

Asks GitHub for the latest published release of the project (drafts and pre-releases are never offered)
and compares its version with this one. Nothing about you or your data is sent: it's a plain request for
the public release list, the same as opening the Releases page in a browser.
"""
import json
import re
import time
import urllib.error
import urllib.request

import inventory as inv

REPO = "rizdem/spoolhouse"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CHECK_EVERY = 24 * 3600


def parse_version(text):
    """'v2.1.0' / '2.1' -> (2, 1, 0); None if it isn't a plain version number."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", (text or "").strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None


def fetch_latest(current, timeout=15):
    """The latest published release as {version, url, published}. Raises IOError with a readable message."""
    req = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"Spoolhouse/{current}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise IOError("No releases have been published yet.")
        if e.code in (403, 429):
            raise IOError("GitHub asked to slow down. It will try again later.")
        raise IOError(f"GitHub answered with an error ({e.code}).")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise IOError("Couldn't reach GitHub. Check your internet connection.")
    if parse_version(data.get("tag_name")) is None:
        raise IOError("The latest release has no version number.")
    url = data.get("html_url") or ""
    if not url.startswith(f"https://github.com/{REPO}/"):
        url = RELEASES_PAGE
    return {"version": data["tag_name"].lstrip("v"), "url": url, "published": data.get("published_at") or ""}


def auto_enabled():
    return inv.get_pref("update_auto", "1") == "1"


def set_auto(on):
    inv.set_pref("update_auto", "1" if on else "0")


def check(current, fetch=fetch_latest):
    """Ask GitHub now and remember the answer. Returns status()."""
    inv.set_pref("update_checked", str(time.time()))
    try:
        inv.set_pref("update_latest", json.dumps(fetch(current)))
        inv.set_pref("update_error", "")
    except IOError as e:
        inv.set_pref("update_error", str(e))
    return status(current)


def due():
    return auto_enabled() and time.time() - float(inv.get_pref("update_checked", "0") or 0) >= CHECK_EVERY


def skip(version):
    inv.set_pref("update_skip", version)


def status(current):
    try:
        latest = json.loads(inv.get_pref("update_latest", "") or "null")
    except ValueError:
        latest = None
    newer = bool(latest and (parse_version(latest["version"]) or ()) > (parse_version(current) or ()))
    skipped = bool(newer and inv.get_pref("update_skip", "") == latest["version"])
    return {"current": current, "auto": auto_enabled(), "latest": latest if newer else None,
            "available": newer and not skipped, "skipped": skipped,
            "checked": float(inv.get_pref("update_checked", "0") or 0) or None,
            "problem": inv.get_pref("update_error", "") or None}


def should_notify(current):
    """The newer release to announce, once per version (remembered across restarts); otherwise None."""
    st = status(current)
    if not st["available"] or inv.get_pref("update_notified", "") == st["latest"]["version"]:
        return None
    inv.set_pref("update_notified", st["latest"]["version"])
    return st["latest"]

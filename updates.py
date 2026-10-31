"""
updates.py - tells you when a newer Spoolhouse is out, and installs it from inside the app.

Asks GitHub for the latest published release of the project (drafts and pre-releases are never offered)
and compares its version with this one. Nothing about you or your data is sent: it's a plain request for
the public release list, the same as opening the Releases page in a browser.

Installing (2.10+): the release's file for this computer is downloaded from GitHub and checked against the
SHA-256 fingerprint GitHub publishes for it (and its size). On a Mac the new app is unpacked and checked (it
must be Spoolhouse, at the expected version), then a small helper swaps it in once this app has quit and
opens it again; the old copy is kept until the swap has worked. On Windows the installer runs with just a
progress bar, into the same folder, and opens Spoolhouse again. Your data lives elsewhere and isn't touched.
"""
import hashlib
import json
import ntpath
import os
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
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
    downloads = f"https://github.com/{REPO}/releases/download/"
    assets = [{"name": a.get("name") or "", "url": a.get("browser_download_url") or "", "size": int(a.get("size") or 0),
               "sha256": (a.get("digest") or "").removeprefix("sha256:").lower()}
              for a in data.get("assets") or [] if (a.get("browser_download_url") or "").startswith(downloads)]
    return {"version": data["tag_name"].lstrip("v"), "url": url, "published": data.get("published_at") or "",
            "assets": assets}


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
    if latest and FORCE:  # testing: offer the latest release even if it's this version (see FORCE)
        newer = True
    skipped = bool(newer and inv.get_pref("update_skip", "") == latest["version"])
    return {"current": current, "auto": auto_enabled(), "latest": latest if newer else None,
            "available": newer and not skipped, "skipped": skipped,
            "checked": float(inv.get_pref("update_checked", "0") or 0) or None,
            "problem": inv.get_pref("update_error", "") or None,
            "can_install": bool(newer and installable(latest)), "install": dict(INSTALL)}


def should_notify(current):
    """The newer release to announce, once per version (remembered across restarts); otherwise None."""
    st = status(current)
    if not st["available"] or inv.get_pref("update_notified", "") == st["latest"]["version"]:
        return None
    inv.set_pref("update_notified", st["latest"]["version"])
    return st["latest"]


# ---------------------------------------------------------------- installing from inside the app
# For testing the whole install on a real computer: start the app with SPOOLHOUSE_UPDATE_FORCE=1 and the latest
# release is offered even if it's the version already installed (so it reinstalls itself).
FORCE = os.environ.get("SPOOLHOUSE_UPDATE_FORCE") == "1"
REOPEN = os.environ.get("SPOOLHOUSE_UPDATE_NO_REOPEN") != "1"  # testing: replace the app but don't open it again
ENDINGS = {"mac-arm64": "-apple-silicon.zip", "mac-x86_64": "-intel.zip", "windows": "-windows-setup.exe"}
INSTALL = {"stage": "", "done": 0, "total": 0, "error": ""}   # what the page shows while installing
_LOCK = threading.Lock()


def this_computer():
    """Which download this copy of Spoolhouse is: mac-arm64, mac-x86_64 (also under Rosetta) or windows."""
    if sys.platform == "darwin":
        return "mac-arm64" if platform.machine() == "arm64" else "mac-x86_64"
    return "windows" if sys.platform == "win32" else ""


def asset_for(latest):
    ending = ENDINGS.get(this_computer())
    return next((a for a in (latest or {}).get("assets") or [] if ending and a["name"].endswith(ending)), None)


def app_bundle():
    """The Spoolhouse.app this is running from (Mac, built app only)."""
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return None
    bundle = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", ".."))
    return bundle if bundle.endswith(".app") else None


def installable(latest):
    """Can this copy install the update itself? Built apps only, with a checked download available, and (on a
    Mac) somewhere it's allowed to replace itself. Otherwise the page offers the download page instead."""
    a = asset_for(latest)
    if not a or not a["sha256"] or not getattr(sys, "frozen", False):
        return False
    if sys.platform == "darwin":
        bundle = app_bundle()
        return bool(bundle) and os.access(os.path.dirname(bundle), os.W_OK) and os.access(bundle, os.W_OK)
    return sys.platform == "win32"


def download(asset, folder, progress=lambda done, total: None, opener=urllib.request.urlopen):
    """Downloads a release file into folder and checks it is exactly what GitHub published. Returns its path."""
    if not asset["url"].startswith(f"https://github.com/{REPO}/releases/download/") or "/" in asset["name"]:
        raise IOError("That download isn't from Spoolhouse's releases.")
    path, h, done = os.path.join(folder, asset["name"]), hashlib.sha256(), 0
    req = urllib.request.Request(asset["url"], headers={"User-Agent": "Spoolhouse updater"})
    try:
        with opener(req, timeout=60) as r, open(path, "wb") as f:
            while chunk := r.read(256 * 1024):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                progress(done, asset["size"])
                if done > asset["size"] + 1024:
                    raise IOError("The download is bigger than it should be.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise IOError(f"The download didn't finish ({getattr(e, 'reason', e)}). Check your internet connection and try again.")
    if done != asset["size"] or h.hexdigest() != asset["sha256"]:
        raise IOError("The download doesn't match the release on GitHub, so it wasn't installed. Try again.")
    return path


def unpack_mac(zip_path, folder, version):
    """Unpacks the new Spoolhouse.app and checks it: our app (same bundle id), at the version expected."""
    out = os.path.join(folder, "new")
    subprocess.run(["/usr/bin/ditto", "-x", "-k", zip_path, out], check=True, capture_output=True)
    app = os.path.join(out, "Spoolhouse.app")
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
    except OSError:
        raise IOError("The download doesn't contain Spoolhouse.")
    if info.get("CFBundleIdentifier") != MAC_BUNDLE_ID or info.get("CFBundleShortVersionString") != version:
        raise IOError("The download isn't the expected version of Spoolhouse, so it wasn't installed.")
    if subprocess.run(["/usr/bin/codesign", "--verify", "--deep", app], capture_output=True).returncode != 0:
        raise IOError("The downloaded app failed its integrity check, so it wasn't installed.")
    subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", app], capture_output=True)
    return app


MAC_BUNDLE_ID = "app.spoolhouse"


def mac_helper(new_app, bundle, pid, log, reopen=True):
    """The script that swaps the app once this one (pid) has quit: old copy kept aside until the new one is in
    place, put back if anything fails; then opens Spoolhouse again."""
    q = shlex.quote
    old = bundle + ".old-update"
    return f"""#!/bin/sh
exec >>{q(log)} 2>&1
echo "$(date) installing update"
i=0; while kill -0 {pid} 2>/dev/null && [ $i -lt 120 ]; do sleep 0.5; i=$((i+1)); done
rm -rf {q(old)}
if mv {q(bundle)} {q(old)} && mv {q(new_app)} {q(bundle)}; then
  rm -rf {q(old)}; echo "updated"
else
  echo "update failed, putting the old app back"; [ -d {q(old)} ] && [ ! -d {q(bundle)} ] && mv {q(old)} {q(bundle)}
fi
{"/usr/bin/open " + q(bundle) if reopen else ":"}
"""


def windows_helper(setup, exe, pid, log):
    """PowerShell that waits for this app to quit, runs the installer quietly into the same folder (all users if it
    was installed in Program Files, which asks Windows for permission), then opens Spoolhouse again."""
    folder = ntpath.dirname(exe)  # Windows paths, whatever this runs on (the tests run on a Mac too)
    program_files = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
    scope = "/ALLUSERS" if any(p and folder.lower().startswith(p.lower()) for p in program_files) else "/CURRENTUSER"
    ps = lambda v: "'" + str(v).replace("'", "''") + "'"
    return f"""Start-Transcript -Path {ps(log)} -Append | Out-Null
Wait-Process -Id {pid} -Timeout 60 -ErrorAction SilentlyContinue
$p = Start-Process -FilePath {ps(setup)} -ArgumentList '/SILENT','/SUPPRESSMSGBOXES','/NORESTART','{scope}',{ps('/DIR="' + folder + '"')} -Wait -PassThru
"installer finished: $($p.ExitCode)"
Start-Process -FilePath {ps(exe)}
"""


def start_install(latest, quit_app, log_path):
    """Downloads, checks and hands over to the helper, in the background; INSTALL tells the page how it's going.
    quit_app() is called once the helper is ready, to close Spoolhouse so it can be replaced."""
    asset = asset_for(latest)
    if not installable(latest):
        raise IOError("This copy of Spoolhouse can't update itself: download the new version instead.")
    with _LOCK:
        if INSTALL["stage"] in ("downloading", "checking", "restarting"):
            return
        INSTALL.update(stage="downloading", done=0, total=asset["size"], error="")

    def run():
        try:
            folder = tempfile.mkdtemp(prefix="spoolhouse-update-")
            path = download(asset, folder, lambda d, t: INSTALL.update(done=d, total=t))
            INSTALL.update(stage="checking")
            if sys.platform == "darwin":
                script = os.path.join(folder, "install.sh")
                with open(script, "w") as f:
                    f.write(mac_helper(unpack_mac(path, folder, latest["version"]), app_bundle(), os.getpid(), log_path, REOPEN))
                subprocess.Popen(["/bin/sh", script], start_new_session=True, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                script = os.path.join(folder, "install.ps1")
                with open(script, "w", encoding="utf-8-sig") as f:
                    f.write(windows_helper(path, sys.executable, os.getpid(), log_path))
                subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                                  "-File", script], creationflags=0x00000008 | 0x00000200,  # detached, own group
                                 close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            INSTALL.update(stage="restarting")
            time.sleep(1.5)  # the page shows "Restarting…" before the window closes
            quit_app()
        except Exception as e:
            INSTALL.update(stage="error", error=str(e) if isinstance(e, IOError) else f"The update didn't install ({e}).")
            shutil.rmtree(folder, ignore_errors=True) if "folder" in locals() else None

    threading.Thread(target=run, daemon=True).start()

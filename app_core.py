"""
app_core.py - what the Mac and Windows apps share: the log file, crash logging, the app's state,
and the plain-language status lines shown in the menu bar / system tray menu.

Imported first by cfs_app.py, so errors are logged even if a later import fails.
"""
import os
import sys
import threading
import traceback

IS_WINDOWS = sys.platform == "win32"


def _log_path():
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return os.path.join(base, "Spoolhouse", "Spoolhouse.log")
    return os.path.expanduser("~/Library/Logs/Spoolhouse.log")


LOG = _log_path()


def log(msg):
    # a windowed app has no terminal, so errors would otherwise vanish
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def _hook(kind, value, tb):
    log("".join(traceback.format_exception(kind, value, tb)))


sys.excepthook = _hook
threading.excepthook = lambda a: _hook(a.exc_type, a.exc_value, a.exc_traceback)

import cfs_gui  # noqa: E402
import inventory as inv  # noqa: E402

cfs_gui.on_error = log

# window: the pywebview window; quitting: Quit was chosen (closing then really quits)
APP = {"window": None, "quitting": False}
MENU_REFRESH_SECS = 10


def frozen():
    """True in the built app, False when run from source."""
    return bool(getattr(sys, "frozen", False))


def menubar_enabled():
    """Keep running in the menu bar (Mac) / system tray (Windows) when the window is closed."""
    return inv.get_pref("menubar", "1") == "1"


def status_lines():
    """Plain-language lines for the menu: each printer, low stock, usage waiting to be charged."""
    lines, used_now = [], None
    spools = {s["id"]: s for s in inv.list_all()}
    links = inv.links()
    for p in inv.list_printers():
        st = cfs_gui.pstate(p["id"])
        job = st["job"] or {}
        if st["error"]:
            text = "Offline"
        elif not st["at"]:
            text = "Checking…"
        elif job.get("state") in ("printing", "paused"):
            used_m = (job.get("used_mm") or 0) / 1000
            used_now = used_m if used_now is None else used_now + used_m
            text = f"{'Paused' if job['state'] == 'paused' else 'Printing'} · {used_m:.1f} m used"
            live = next((s for s in (st["data"] or {}).get("slots", []) if s.get("printing")), None)
            ln = links.get(live["key"]) if live else None
            sp = spools.get(ln["spool_id"]) if ln else None
            if sp:
                text += f" · {sp['remaining_g']:.0f} g left"
        else:
            text = "Idle"
        lines.append(f"{p['name']}: {text}")
    if not lines:
        lines.append("No printers added")
    low = inv.get_settings()["low_g"]
    groups = {}
    for s in spools.values():
        groups[(s["material"], s["color"])] = groups.get((s["material"], s["color"]), 0) + s["remaining_g"]
    n_low = sum(1 for v in groups.values() if 0 < v < low)
    if n_low:
        lines.append(f"Running low: {n_low} filament{'s' if n_low > 1 else ''}")
    n_un = sum(1 for u in inv.recent_usage(200) if not u["spool_id"])
    if n_un:
        lines.append(f"{n_un} usage entr{'ies' if n_un > 1 else 'y'} to charge")
    return lines, used_now


def safe_status_lines():
    try:
        return status_lines()
    except Exception as e:  # never let the menu break the app
        return [f"Status unavailable ({e})"], None

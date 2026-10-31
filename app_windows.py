"""
app_windows.py - the Windows side of the app: system tray icon and menu, Start with Windows (a
per-user Run entry in the registry), notifications from the tray icon, and one copy at a time.

The tray icon shows while Spoolhouse runs. With "Keep running in the system tray" on (the default),
closing the window leaves it running there, so printer usage keeps coming off your stock.
"""
import ctypes
import json
import os
import sys
import threading
import time
import urllib.request
import winreg

import pystray
from PIL import Image

import app_core as core
import cfs_gui

APP = core.APP
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Spoolhouse"
MUTEX_NAME = "Local\\Spoolhouse"
ERROR_ALREADY_EXISTS = 183
WIN = {"icon": None, "mutex": None}

TRAY_NAME = "system tray"
LOGIN_LABEL = "Start with Windows"


# ---------------------------------------------------------------- start with Windows
def login_available():
    return core.frozen()


def login_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, RUN_VALUE)[0])
    except OSError:
        return False


def set_login(on):
    """The same per-user entry as Task Manager's Startup tab: opens Spoolhouse in the tray at sign-in."""
    if on:
        if not core.frozen():
            raise IOError("Start with Windows works in the installed app, not when running from source.")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, f'"{sys.executable}" --background')
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- one copy at a time
def before_start():
    """A second launch (e.g. the Start menu while it's in the tray) brings the running copy forward."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    WIN["mutex"] = kernel32.CreateMutexW(None, False, MUTEX_NAME)  # kept open for the app's lifetime
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{cfs_gui.PORT}/api/app/show", data=b"{}",
                                         headers={"X-CFS": "1", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
        except OSError as e:
            core.log(f"already running, but couldn't bring it forward: {e}")
        os._exit(0)


def window_options():
    """Keep the window's web data (remembered filters, page) in the user's own folder: the install
    folder under Program Files isn't writable."""
    data = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local"),
                        "Spoolhouse", "WebView")
    os.makedirs(data, exist_ok=True)
    return {}, {"private_mode": False, "storage_path": data}


# ---------------------------------------------------------------- window
def show_window():
    w = APP["window"]
    w.show()
    w.restore()  # un-minimise


def hide_window():
    APP["window"].hide()


def quit_now():
    """Quit for real, from any thread (e.g. so the installer can replace the app)."""
    quit_app()


def quit_app():
    APP["quitting"] = True
    cfs_gui.CANCEL.set()
    on_quit()
    APP["window"].destroy()


def on_quit():
    if WIN["icon"] is not None:
        try:
            WIN["icon"].stop()
        except Exception:
            pass


# ---------------------------------------------------------------- system tray
def _toggle_login(icon, item):
    try:
        set_login(not login_enabled())
    except IOError as e:
        core.log(str(e))
    refresh_menu()


def _menu_items():
    lines, _ = core.safe_status_lines()
    items = [pystray.MenuItem(cfs_gui.APP_NAME, None, enabled=False)]
    items += [pystray.MenuItem(ln, None, enabled=False) for ln in lines]
    items += [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Open {cfs_gui.APP_NAME}", lambda icon, item: show_window(), default=True),
        pystray.MenuItem(LOGIN_LABEL, _toggle_login, checked=lambda item: login_enabled(),
                         enabled=login_available()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Quit {cfs_gui.APP_NAME}", lambda icon, item: quit_app()),
    ]
    return items


def _tooltip():
    lines, used_now = core.safe_status_lines()
    text = cfs_gui.APP_NAME + (f" · {used_now:.1f} m" if used_now is not None else "") + "\n" + "\n".join(lines)
    return text[:127]  # Windows' limit for tray tooltips


def refresh_menu():
    icon = WIN["icon"]
    if icon is not None:
        icon.title = _tooltip()
        icon.update_menu()


def _menu_loop():
    while True:
        time.sleep(core.MENU_REFRESH_SECS)
        refresh_menu()


def on_started(background):
    """Runs once the window is up (on pywebview's thread): the tray icon gets its own thread."""
    image = Image.open(os.path.join(cfs_gui.web_dir(), "img", "icon.png"))
    WIN["icon"] = pystray.Icon("Spoolhouse", image, _tooltip(), pystray.Menu(lambda: iter(_menu_items())))
    threading.Thread(target=WIN["icon"].run, daemon=True).start()
    threading.Thread(target=_menu_loop, daemon=True).start()


def notify(title, body):
    """A Windows notification from the tray icon."""
    icon = WIN["icon"]
    if icon is None:
        raise IOError("The tray icon isn't ready yet.")
    icon.notify(body, title)


def self_test():
    """For the build: check the pieces only the installed app uses load, then exit."""
    core.log("self-test windows: " + json.dumps({"pystray": pystray.__name__, "pil": Image.__name__}))

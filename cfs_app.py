#!/usr/bin/env python3
"""
cfs_app.py - Spoolhouse, the desktop app (macOS and Windows): filament inventory and Creality CFS tags.

Runs the same local server as cfs_gui.py on 127.0.0.1 and shows it in a window (WebKit on macOS,
Edge WebView2 on Windows). Closing the window keeps the app running in the menu bar / system tray
(so printer usage is still tracked) unless that's turned off in Settings; Quit really quits.
The platform-specific parts are in app_mac.py and app_windows.py.

    python3 -m pip install -r requirements.txt
    python3 cfs_app.py                 # add --background to start hidden in the menu bar / tray
    python3 cfs_app.py --self-test     # check everything loads and the server answers, then exit
"""
import os
import sys
import threading

import app_core as core  # first: sets up logging of any error below

import webview  # noqa: E402

import cfs_gui  # noqa: E402
import inventory as inv  # noqa: E402
import phone_access  # noqa: E402

if core.IS_WINDOWS:
    import app_windows as ui  # noqa: E402
else:
    import app_mac as ui  # noqa: E402

PREFERRED_PORT = cfs_gui.PORT  # fixed port keeps the page's remembered settings between runs
APP = core.APP


def on_closing():
    if APP["quitting"] or not core.menubar_enabled():
        cfs_gui.CANCEL.set()  # release a pending tag wait so nothing is left holding the reader
        ui.on_quit()
        return True
    ui.hide_window()
    ui.refresh_menu()
    return False  # keep running in the menu bar / tray


# ---------------------------------------------------------------- settings hooks for the page
def _native_settings(values=None):
    if values:
        if "menubar" in values:
            inv.set_pref("menubar", "1" if values["menubar"] else "0")
        if "login" in values:
            ui.set_login(bool(values["login"]))
        ui.refresh_menu()
    return {"native": True, "menubar": core.menubar_enabled(), "login": ui.login_enabled(),
            "login_available": ui.login_available()}


def _first(result):
    """pywebview returns a path, a list of paths, or None."""
    if not result:
        return None
    return result[0] if isinstance(result, (list, tuple)) else result


def _choose_folder():
    return _first(APP["window"].create_file_dialog(webview.FOLDER_DIALOG))


def _save_file(name):
    return _first(APP["window"].create_file_dialog(
        webview.SAVE_DIALOG, directory=os.path.expanduser("~/Documents"), save_filename=name))


def _open_file():
    return _first(APP["window"].create_file_dialog(
        webview.OPEN_DIALOG, file_types=("Spoolhouse backups (*.db)", "All files (*.*)")))


cfs_gui.NATIVE.update(settings=_native_settings, choose_folder=_choose_folder, save_file=_save_file,
                      open_file=_open_file, notify=ui.notify, show=ui.show_window, quit=ui.quit_now)


# ---------------------------------------------------------------- start
def start_server(port=PREFERRED_PORT):
    try:
        srv = cfs_gui.LocalServer(("127.0.0.1", port), cfs_gui.Handler)
    except OSError:  # port busy (e.g. cfs_gui.py still running) - take any free one
        srv = cfs_gui.LocalServer(("127.0.0.1", 0), cfs_gui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    core.log(f"server listening on {srv.server_address}")
    return srv


def self_test():
    """Used by the builds: everything the app needs loads, and its server answers. Exits 0 or 1."""
    import json
    import tempfile
    import urllib.request
    import smartcard.System  # noqa: F401 - the reader library, with its native part
    # a throwaway data folder: the check must never touch anyone's real inventory
    inv.DATA_DIR = tempfile.mkdtemp(prefix="spoolhouse-self-test-")
    inv.DB_PATH = os.path.join(inv.DATA_DIR, "inventory.db")
    srv = start_server(port=0)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    page = urllib.request.urlopen(url, timeout=10).read().decode()
    req = urllib.request.Request(url + "/api/inv/list", data=b"{}", headers={"X-CFS": "1"})
    spools = json.load(urllib.request.urlopen(req, timeout=10))["spools"]
    ok = cfs_gui.APP_NAME in page and isinstance(spools, list)
    # Phone access: its own encrypted server, the pairing QR code, and the network announcement library
    from zeroconf import ServiceInfo, Zeroconf  # noqa: F401 - packaged with its native parts?
    phone = phone_access.start(port=0, host="127.0.0.1", announce=False)
    qr = phone_access.start_pairing()
    phone_ok = len(phone["fingerprint"] or "") == 64 and qr["qr_svg"].startswith("<svg")
    phone_access.stop()
    ok = ok and phone_ok
    if hasattr(ui, "self_test"):
        ui.self_test()
    result = (f"self-test {'passed' if ok else 'FAILED'}: {cfs_gui.APP_NAME} {cfs_gui.APP_VERSION}, "
              f"page {len(page)} bytes, {len(spools)} spools, phone access {'ok' if phone_ok else 'FAILED'}, "
              f"data in {inv.DATA_DIR}")
    core.log(result)  # a windowed Windows .exe has no console, so the build reads the log
    if sys.stdout:
        print(result, flush=True)
    os._exit(0 if ok else 1)


def main():
    if "--self-test" in sys.argv:
        self_test()
    ui.before_start()
    background = "--background" in sys.argv and core.menubar_enabled()
    srv = start_server()
    cfs_gui.start_printer_sync()  # charges spools for printer usage while the app runs
    cfs_gui.start_backup_scheduler()  # automatic backups to the chosen folder (e.g. a NAS)
    cfs_gui.start_watchers()  # low stock, prints to charge and the reader, for notifications
    cfs_gui.start_update_checker()  # once a day: is a newer version out on GitHub?
    phone_access.start_if_enabled()  # the phone app's connection, if switched on in Settings
    window_extras, start_extras = ui.window_options()
    APP["window"] = webview.create_window(
        cfs_gui.APP_NAME, f"http://127.0.0.1:{srv.server_address[1]}",
        width=1040, height=800, min_size=(760, 560), hidden=background, **window_extras,
    )
    APP["window"].events.closing += on_closing
    core.log("starting" + (f" in the {ui.TRAY_NAME}" if background else " window"))
    webview.start(ui.on_started, background, **start_extras)
    core.log("quit")
    os._exit(0)  # don't wait on any in-flight reader or printer call


if __name__ == "__main__":
    main()

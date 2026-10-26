#!/usr/bin/env python3
"""
cfs_app.py - Spoolhouse for macOS: filament inventory and Creality CFS tags.

Runs the same local server as cfs_gui.py on 127.0.0.1 and shows it in a WebKit window.
Closing the window keeps the app running in the menu bar (so printer usage is still tracked)
unless that's turned off in Settings; Quit (⌘Q or the menu bar) really quits.

    python3 -m pip install -r requirements.txt
    python3 cfs_app.py                 # add --background to start hidden in the menu bar
"""
import os
import plistlib
import sys
import threading
import time
import traceback

LOG = os.path.expanduser("~/Library/Logs/Spoolhouse.log")


def _log(msg):
    # a windowed .app has no terminal, so errors would otherwise vanish
    try:
        with open(LOG, "a") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def _hook(kind, value, tb):
    _log("".join(traceback.format_exception(kind, value, tb)))


sys.excepthook = _hook
threading.excepthook = lambda a: _hook(a.exc_type, a.exc_value, a.exc_traceback)

import AppKit  # noqa: E402
import Foundation  # noqa: E402
import webview  # noqa: E402
from PyObjCTools import AppHelper  # noqa: E402

import cfs_gui  # noqa: E402
import inventory as inv  # noqa: E402

PREFERRED_PORT = cfs_gui.PORT  # fixed port keeps the page's remembered settings between runs
AGENT_LABEL = "app.spoolhouse"
OLD_AGENT_PLIST = os.path.expanduser("~/Library/LaunchAgents/local.cfs.tagwriter.plist")  # before 2.0
AGENT_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{AGENT_LABEL}.plist")
MENU_REFRESH_SECS = 10

APP = {"window": None, "quitting": False, "item": None, "target": None, "delegate": None}

cfs_gui.on_error = _log


# ---------------------------------------------------------------- open at login
def bundle_path():
    """Path of the running .app, or None when run from source."""
    if getattr(sys, "frozen", False):
        app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))))
        return app if app.endswith(".app") else None
    return None


def login_enabled():
    return os.path.exists(AGENT_PLIST)


def set_login(on):
    """A per-user LaunchAgent that opens the app hidden (menu bar only) when you log in."""
    if on:
        app = bundle_path()
        if not app:
            raise IOError("Open at login works in the built app, not when running from source.")
        os.makedirs(os.path.dirname(AGENT_PLIST), exist_ok=True)
        with open(AGENT_PLIST, "wb") as f:
            plistlib.dump({"Label": AGENT_LABEL, "RunAtLoad": True,
                           "ProgramArguments": ["/usr/bin/open", "-g", "-a", app, "--args", "--background"]}, f)
    elif os.path.exists(AGENT_PLIST):
        os.remove(AGENT_PLIST)


def carry_over_login_item():
    """Before 2.0 the login item was CFS Tag Writer's: if it was on, swap it for Spoolhouse's."""
    if os.path.exists(OLD_AGENT_PLIST):
        os.remove(OLD_AGENT_PLIST)
        if bundle_path():
            set_login(True)


def menubar_enabled():
    return inv.get_pref("menubar", "1") == "1"


# ---------------------------------------------------------------- window
def show_window():
    def go():
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)  # Dock icon back
        APP["window"].show()
        AppKit.NSApp.activateIgnoringOtherApps_(True)
    AppHelper.callAfter(go)


def hide_window():
    APP["window"].hide()
    # menu bar only while hidden: no Dock icon or app switcher entry
    AppHelper.callAfter(lambda: AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory))


def on_closing():
    if APP["quitting"] or not menubar_enabled():
        cfs_gui.CANCEL.set()  # release a pending tag wait so nothing is left holding the reader
        return True
    hide_window()
    refresh_menu()
    return False  # keep running in the menu bar


class CFSAppDelegate(AppKit.NSObject):
    def applicationShouldTerminate_(self, app):
        # ⌘Q / Quit really quits (the window's close button only hides it)
        APP["quitting"] = True
        cfs_gui.CANCEL.set()
        return AppKit.NSTerminateNow

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
        show_window()  # clicking the Dock icon brings the window back
        return False

    def applicationSupportsSecureRestorableState_(self, app):
        return True


# ---------------------------------------------------------------- menu bar
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


class CFSMenuTarget(AppKit.NSObject):
    def openWindow_(self, sender):
        show_window()

    def toggleLogin_(self, sender):
        try:
            set_login(not login_enabled())
        except IOError as e:
            _log(str(e))
        refresh_menu()

    def quit_(self, sender):
        APP["quitting"] = True
        AppKit.NSApp.terminate_(None)


def _add(menu, title, action=None, key="", enabled=True, state=None):
    it = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
    if action:
        it.setTarget_(APP["target"])
    it.setEnabled_(enabled)
    if state is not None:
        it.setState_(AppKit.NSControlStateValueOn if state else AppKit.NSControlStateValueOff)
    menu.addItem_(it)
    return it


def _build_menu():
    """Runs on the main thread."""
    if not menubar_enabled():
        if APP["item"]:
            AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(APP["item"])
            APP["item"] = None
        return
    if APP["item"] is None:
        item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        img = AppKit.NSImage.alloc().initWithContentsOfFile_(os.path.join(cfs_gui.web_dir(), "img", "menubar.svg"))
        if img:
            img.setSize_((18, 18))
            img.setTemplate_(True)
            item.button().setImage_(img)
        else:
            item.button().setTitle_("CFS")
        APP["item"] = item
    try:
        lines, used_now = status_lines()
    except Exception as e:  # never let the menu break the app
        lines, used_now = [f"Status unavailable ({e})"], None
    btn = APP["item"].button()
    btn.setTitle_(f" {used_now:.1f} m" if used_now is not None else "")
    btn.setToolTip_(cfs_gui.APP_NAME + "\n" + "\n".join(lines))
    menu = AppKit.NSMenu.alloc().init()
    menu.setAutoenablesItems_(False)
    _add(menu, cfs_gui.APP_NAME, enabled=False)
    for ln in lines:
        _add(menu, ln, enabled=False)
    menu.addItem_(AppKit.NSMenuItem.separatorItem())
    _add(menu, f"Open {cfs_gui.APP_NAME}", "openWindow:", "o")
    _add(menu, "Open at login", "toggleLogin:", state=login_enabled(), enabled=bundle_path() is not None)
    menu.addItem_(AppKit.NSMenuItem.separatorItem())
    _add(menu, f"Quit {cfs_gui.APP_NAME}", "quit:", "q")
    APP["item"].setMenu_(menu)


def refresh_menu():
    AppHelper.callAfter(_build_menu)


def _menu_loop():
    while True:
        refresh_menu()
        time.sleep(MENU_REFRESH_SECS)


def _on_started(background):
    """Runs once the window system is up (on pywebview's thread)."""
    def setup():
        APP["target"] = CFSMenuTarget.alloc().init()
        APP["delegate"] = CFSAppDelegate.alloc().init()
        AppKit.NSApp.setDelegate_(APP["delegate"])
        if background:
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        _build_menu()
        _setup_notifications()
    AppHelper.callAfter(setup)
    threading.Thread(target=_menu_loop, daemon=True).start()


# ---------------------------------------------------------------- settings hooks for the page
def _native_settings(values=None):
    if values:
        if "menubar" in values:
            inv.set_pref("menubar", "1" if values["menubar"] else "0")
        if "login" in values:
            set_login(bool(values["login"]))
        refresh_menu()
    return {"native": True, "menubar": menubar_enabled(), "login": login_enabled(),
            "login_available": bundle_path() is not None}


# ---------------------------------------------------------------- notifications
NOTIFY = {"center": None, "delegate": None}


class CFSNotifyDelegate(AppKit.NSObject):
    def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, note, handler):
        import UserNotifications as UN
        handler(UN.UNNotificationPresentationOptionBanner | UN.UNNotificationPresentationOptionList
                | UN.UNNotificationPresentationOptionSound)  # show banners even while the app is in front

    def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(self, center, response, handler):
        show_window()  # clicking a notification opens the app
        handler()


def _setup_notifications():
    """Use Apple's notification centre in the built app (it needs a real app bundle)."""
    if bundle_path() is None:
        return
    try:
        import UserNotifications as UN
        center = UN.UNUserNotificationCenter.currentNotificationCenter()
        NOTIFY["delegate"] = CFSNotifyDelegate.alloc().init()
        center.setDelegate_(NOTIFY["delegate"])
        center.requestAuthorizationWithOptions_completionHandler_(
            UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound,
            lambda granted, err: _log(f"notifications allowed: {bool(granted)}" + (f" ({err})" if err else "")))
        NOTIFY["center"] = center
    except Exception as e:
        _log(f"notifications unavailable: {e}")


def _notify(title, body):
    if NOTIFY["center"] is not None:
        import uuid
        import UserNotifications as UN
        content = UN.UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setBody_(body)
        content.setSound_(UN.UNNotificationSound.defaultSound())
        req = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(str(uuid.uuid4()), content, None)
        NOTIFY["center"].addNotificationRequest_withCompletionHandler_(
            req, lambda err: err and _log(f"notification failed: {err}"))
        return
    # running from source: no app bundle, so fall back to a plain system notification
    import subprocess
    q = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    subprocess.run(["osascript", "-e", f"display notification {q(body)} with title {q(title)}"],
                   check=False, timeout=10)


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


cfs_gui.NATIVE.update(settings=_native_settings, choose_folder=_choose_folder,
                      save_file=_save_file, open_file=_open_file, notify=_notify)


# ---------------------------------------------------------------- start
def start_server():
    try:
        srv = cfs_gui.LocalServer(("127.0.0.1", PREFERRED_PORT), cfs_gui.Handler)
    except OSError:  # port busy (e.g. cfs_gui.py still running) - take any free one
        srv = cfs_gui.LocalServer(("127.0.0.1", 0), cfs_gui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _log(f"server listening on {srv.server_address}")
    return srv


def main():
    carry_over_login_item()
    background = "--background" in sys.argv and menubar_enabled()
    srv = start_server()
    cfs_gui.start_printer_sync()  # charges spools for printer usage while the app runs
    cfs_gui.start_backup_scheduler()  # automatic backups to the chosen folder (e.g. a NAS)
    cfs_gui.start_watchers()  # low stock, prints to charge and the reader, for notifications
    cfs_gui.start_update_checker()  # once a day: is a newer version out on GitHub?
    APP["window"] = webview.create_window(
        cfs_gui.APP_NAME, f"http://127.0.0.1:{srv.server_address[1]}",
        width=1040, height=800, min_size=(760, 560), hidden=background,
    )
    APP["window"].events.closing += on_closing
    _log("starting" + (" in the menu bar" if background else " window"))
    webview.start(_on_started, background)
    _log("quit")
    os._exit(0)  # don't wait on any in-flight reader or printer call


if __name__ == "__main__":
    main()

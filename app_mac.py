"""
app_mac.py - the macOS side of the app: menu bar item, Open at login (a LaunchAgent), Dock icon
handling and notifications through Apple's notification centre.
"""
import os
import plistlib
import sys
import threading
import time

import AppKit
from PyObjCTools import AppHelper

import app_core as core
import cfs_gui

APP = core.APP
AGENT_LABEL = "app.spoolhouse"
OLD_AGENT_PLIST = os.path.expanduser("~/Library/LaunchAgents/local.cfs.tagwriter.plist")  # before 2.0
AGENT_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{AGENT_LABEL}.plist")
MAC = {"item": None, "target": None, "delegate": None}

TRAY_NAME = "menu bar"
LOGIN_LABEL = "Open at login"


# ---------------------------------------------------------------- open at login
def bundle_path():
    """Path of the running .app, or None when run from source."""
    if core.frozen():
        app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))))
        return app if app.endswith(".app") else None
    return None


def login_available():
    return bundle_path() is not None


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


def before_start():
    """Before 2.0 the login item was CFS Tag Writer's: if it was on, swap it for Spoolhouse's."""
    if os.path.exists(OLD_AGENT_PLIST):
        os.remove(OLD_AGENT_PLIST)
        if bundle_path():
            set_login(True)


def window_options():
    return {}, {}  # (create_window extras, webview.start extras): the defaults suit macOS


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


def on_quit():
    pass  # nothing extra: the menu bar item goes with the app


def quit_now():
    """Quit for real, from any thread (e.g. so an update can replace the app)."""
    APP["quitting"] = True
    AppHelper.callAfter(lambda: AppKit.NSApp.terminate_(None))


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
class CFSMenuTarget(AppKit.NSObject):
    def openWindow_(self, sender):
        show_window()

    def toggleLogin_(self, sender):
        try:
            set_login(not login_enabled())
        except IOError as e:
            core.log(str(e))
        refresh_menu()

    def quit_(self, sender):
        APP["quitting"] = True
        AppKit.NSApp.terminate_(None)


def _add(menu, title, action=None, key="", enabled=True, state=None):
    it = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
    if action:
        it.setTarget_(MAC["target"])
    it.setEnabled_(enabled)
    if state is not None:
        it.setState_(AppKit.NSControlStateValueOn if state else AppKit.NSControlStateValueOff)
    menu.addItem_(it)
    return it


def _build_menu():
    """Runs on the main thread."""
    if not core.menubar_enabled():
        if MAC["item"]:
            AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(MAC["item"])
            MAC["item"] = None
        return
    if MAC["item"] is None:
        item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        img = AppKit.NSImage.alloc().initWithContentsOfFile_(os.path.join(cfs_gui.web_dir(), "img", "menubar.svg"))
        if img:
            img.setSize_((18, 18))
            img.setTemplate_(True)
            item.button().setImage_(img)
        else:
            item.button().setTitle_("CFS")
        MAC["item"] = item
    lines, used_now = core.safe_status_lines()
    btn = MAC["item"].button()
    btn.setTitle_(f" {used_now:.1f} m" if used_now is not None else "")
    btn.setToolTip_(cfs_gui.APP_NAME + "\n" + "\n".join(lines))
    menu = AppKit.NSMenu.alloc().init()
    menu.setAutoenablesItems_(False)
    _add(menu, cfs_gui.APP_NAME, enabled=False)
    for ln in lines:
        _add(menu, ln, enabled=False)
    menu.addItem_(AppKit.NSMenuItem.separatorItem())
    _add(menu, f"Open {cfs_gui.APP_NAME}", "openWindow:", "o")
    _add(menu, LOGIN_LABEL, "toggleLogin:", state=login_enabled(), enabled=login_available())
    menu.addItem_(AppKit.NSMenuItem.separatorItem())
    _add(menu, f"Quit {cfs_gui.APP_NAME}", "quit:", "q")
    MAC["item"].setMenu_(menu)


def refresh_menu():
    AppHelper.callAfter(_build_menu)


def _menu_loop():
    while True:
        refresh_menu()
        time.sleep(core.MENU_REFRESH_SECS)


def on_started(background):
    """Runs once the window system is up (on pywebview's thread)."""
    def setup():
        MAC["target"] = CFSMenuTarget.alloc().init()
        MAC["delegate"] = CFSAppDelegate.alloc().init()
        AppKit.NSApp.setDelegate_(MAC["delegate"])
        if background:
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        _build_menu()
        _setup_notifications()
    AppHelper.callAfter(setup)
    threading.Thread(target=_menu_loop, daemon=True).start()


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
            lambda granted, err: core.log(f"notifications allowed: {bool(granted)}" + (f" ({err})" if err else "")))
        NOTIFY["center"] = center
    except Exception as e:
        core.log(f"notifications unavailable: {e}")


def notify(title, body):
    if NOTIFY["center"] is not None:
        import uuid
        import UserNotifications as UN
        content = UN.UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setBody_(body)
        content.setSound_(UN.UNNotificationSound.defaultSound())
        req = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(str(uuid.uuid4()), content, None)
        NOTIFY["center"].addNotificationRequest_withCompletionHandler_(
            req, lambda err: err and core.log(f"notification failed: {err}"))
        return
    # running from source: no app bundle, so fall back to a plain system notification
    import subprocess
    q = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'  # noqa: E731
    subprocess.run(["osascript", "-e", f"display notification {q(body)} with title {q(title)}"],
                   check=False, timeout=10)

"""Try a concept on the built app: .venv/bin/python branding/try_icon.py b
Puts that icon on dist/Spoolhouse.app and relaunches it, so you see it in the Dock and Finder.
Only for trying: the final choice gets built in by build_app.sh."""
import glob, os, subprocess, sys, time
import AppKit

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "dist", "Spoolhouse.app")
letter = (sys.argv[1:] or [""])[0].lower()
found = glob.glob(os.path.join(HERE, "icons", f"{letter}-*.icns")) if letter else []
if len(found) != 1:
    sys.exit("Usage: try_icon.py <a|b|c|d|e>   (run make_icons.py first)")
img = AppKit.NSImage.alloc().initWithContentsOfFile_(found[0])
if not AppKit.NSWorkspace.sharedWorkspace().setIcon_forFile_options_(img, APP, 0):
    sys.exit("Couldn't set the icon on " + APP)
subprocess.run(["osascript", "-e", 'tell application "Spoolhouse" to quit'], capture_output=True)
time.sleep(2)
subprocess.run(["touch", APP]); subprocess.run(["killall", "Dock"])  # refresh the icon cache
time.sleep(1)
subprocess.run(["open", APP])
print("Spoolhouse now shows", os.path.basename(found[0]))

"""Release notes for a version: install steps for the three downloads, then that version's CHANGELOG entry.

    python3 tools/release_notes.py 2.4.0 > notes.md
"""
import os
import re
import sys

version = sys.argv[1]
changelog = open(os.path.join(os.path.dirname(__file__), "..", "CHANGELOG.md"), encoding="utf-8").read()
m = re.search(rf"^## {re.escape(version)} .*?$(.*?)(?=^## |\Z)", changelog, re.M | re.S)
if not m:
    sys.exit(f"No CHANGELOG entry for {version}")
print(f"""**Spoolhouse** is a free app for your filament: write and read Creality CFS RFID tags, keep an inventory of every spool, and track what each print uses on Creality K-series printers.

### Download
| Your computer | Download |
|---|---|
| Mac with Apple Silicon (M1 or later), macOS 11+ | `Spoolhouse-{version}-apple-silicon.zip` |
| Intel Mac, macOS 10.15 Catalina or later | `Spoolhouse-{version}-intel.zip` |
| Windows 10 or 11 (64-bit) | `Spoolhouse-{version}-windows-setup.exe` |

**Mac:** unzip, drag Spoolhouse into Applications. The first time, open System Settings → Privacy & Security and click **Open Anyway**.
**Windows:** run the installer (no administrator needed). If SmartScreen warns about an unrecognised app, click **More info → Run anyway**.

Your data is kept when you update.

---
""")
print(re.sub(r"^### ", "#### ", m.group(1).strip(), flags=re.M))

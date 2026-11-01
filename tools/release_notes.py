"""Release notes for a version: just that version's CHANGELOG entry.

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
print(m.group(1).strip())

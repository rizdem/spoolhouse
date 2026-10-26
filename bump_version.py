#!/usr/bin/env python3
"""
bump_version.py - bump the app version (semantic versioning) and open a CHANGELOG entry.

    python3 bump_version.py patch   # 1.0.0 -> 1.0.1  bug fixes, small tweaks
    python3 bump_version.py minor   # 1.0.1 -> 1.1.0  new features
    python3 bump_version.py major   # 1.1.0 -> 2.0.0  big / breaking changes

The version lives in cfs_gui.py (APP_VERSION); build_app.sh stamps it into the app and zip name.
"""
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "cfs_gui.py"
CHANGELOG = ROOT / "CHANGELOG.md"
PATTERN = re.compile(r'^APP_VERSION = "(\d+)\.(\d+)\.(\d+)"$', re.M)


def main():
    part = sys.argv[1] if len(sys.argv) > 1 else ""
    if part not in ("major", "minor", "patch"):
        sys.exit(__doc__)
    text = SRC.read_text()
    m = PATTERN.search(text)
    if not m:
        sys.exit("APP_VERSION not found in cfs_gui.py")
    major, minor, patch = map(int, m.groups())
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    old, new = ".".join(m.groups()), f"{major}.{minor}.{patch}"
    SRC.write_text(PATTERN.sub(f'APP_VERSION = "{new}"', text, count=1))

    heading = {"major": "### Changed", "minor": "### Added", "patch": "### Fixed"}[part]
    entry = f"## {new} - {datetime.date.today().isoformat()}\n\n{heading}\n- \n\n"
    log = CHANGELOG.read_text() if CHANGELOG.exists() else "# Changelog\n\n"
    head, _, rest = log.partition("\n## ")
    CHANGELOG.write_text(f"{head.rstrip()}\n\n{entry}" + (f"## {rest}" if rest else ""))
    print(f"{old} -> {new}  (fill in the new entry in CHANGELOG.md)")


if __name__ == "__main__":
    main()

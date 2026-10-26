"""Fail if any binary in a built .app needs a newer macOS than the app promises.

    python tools/check_minos.py dist/intel/Spoolhouse.app 10.15 x86_64

(An Intel Mac download once picked up a library built for macOS 15 without anyone noticing.)"""
import os
import re
import subprocess
import sys


def needs(path, arch):
    out = subprocess.run(["otool", "-arch", arch, "-l", path], capture_output=True, text=True).stdout
    m = re.search(r"LC_BUILD_VERSION.*?minos (\S+)|LC_VERSION_MIN_MACOSX.*?version (\S+)", out, re.S)
    return tuple(int(x) for x in (m.group(1) or m.group(2)).split(".")) if m else None


def main(app, min_os, arch):
    limit = tuple(int(x) for x in min_os.split("."))
    bad = []
    for root, _, files in os.walk(app):
        for f in files:
            p = os.path.join(root, f)
            if os.path.islink(p) or not (f.endswith((".so", ".dylib")) or os.access(p, os.X_OK)):
                continue
            v = needs(p, arch)
            if v and v > limit:
                bad.append((".".join(map(str, v)), os.path.relpath(p, app)))
    for v, p in sorted(bad, reverse=True):
        print(f"  needs macOS {v}: {p}")
    print(f"macOS check ({arch}): {'OK, everything runs on ' + min_os + '+' if not bad else str(len(bad)) + ' file(s) need a newer macOS'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))

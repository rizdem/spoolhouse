#!/bin/bash
# Rewrite requirements.lock: the exact version (and file hashes) of every package the app is built and
# tested with, for macOS (Apple Silicon and Intel) and Windows at once. Builds and tests install from this,
# so what you test is what ships.
#   tools/update_lock.sh             keep the versions already locked, add or drop what requirements*.txt changed
#   tools/update_lock.sh --upgrade   move everything to the newest versions requirements*.txt allows
# Then run the tests, build and test the apps (tests/test_requirements_lock.py checks the two files agree).
set -e
cd "$(dirname "$0")/.."
uv pip compile --universal --generate-hashes --python-version 3.12 "$@" \
    --custom-compile-command "tools/update_lock.sh" requirements-dev.txt -o requirements.lock

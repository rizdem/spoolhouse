#!/bin/bash
# Build "Spoolhouse.app" for Apple Silicon into ./dist, plus a zip for GitHub releases.
#
# One-time setup (native arm64 Python in ./.venv, separate from any Intel/Rosetta Python):
#   uv venv --python 3.12 --python-preference only-managed .venv
#   uv pip install --python .venv/bin/python -r requirements-dev.txt
set -e
cd "$(dirname "$0")"

.venv/bin/python -m pytest -q || { echo "Tests failed - not building."; exit 1; }

PY=.venv/bin/python
[ -x "$PY" ] || { echo "No .venv found - see the setup lines at the top of this script."; exit 1; }
[ "$("$PY" -c 'import platform; print(platform.machine())')" = arm64 ] || { echo ".venv Python isn't arm64."; exit 1; }

VERSION=$("$PY" -c 'import cfs_gui; print(cfs_gui.APP_VERSION)')
NAME=$("$PY" -c 'import cfs_gui; print(cfs_gui.APP_NAME)')
ICON=()  # the chosen app icon, once there is one (see branding/)
[ -f branding/Spoolhouse.icns ] && ICON=(--icon "$PWD/branding/Spoolhouse.icns")

"$PY" -m PyInstaller --noconfirm --clean --windowed --name "$NAME" \
  --target-arch arm64 \
  --osx-bundle-identifier app.spoolhouse \
  --distpath dist --workpath build_tmp --specpath build_tmp --paths "$PWD" \
  --add-data "$PWD/web:web" "${ICON[@]}" \
  --collect-submodules webview --collect-submodules smartcard cfs_app.py

# stamp the version into Info.plist so Finder's Get Info shows it
PLIST="dist/$NAME.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST"
codesign --force --deep --sign - "dist/$NAME.app"  # re-seal after the plist edit (ad-hoc)

rm -rf build_tmp "dist/$NAME"
ZIP="dist/$NAME-$VERSION-apple-silicon.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "dist/$NAME.app" "$ZIP"
echo "Built: $PWD/dist/$NAME.app ($VERSION, arm64)"
echo "Zip:   $PWD/$ZIP"

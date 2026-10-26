#!/bin/bash
# Build "Spoolhouse.app" into ./dist, plus a zip for GitHub releases.
#
#   ./build_app.sh          Apple Silicon -> dist/Spoolhouse.app,       Spoolhouse-<v>-apple-silicon.zip
#   ./build_app.sh intel    Intel Macs    -> dist/intel/Spoolhouse.app, Spoolhouse-<v>-intel.zip
#   ./build_app.sh all      both
#
# One-time setup. Apple Silicon (native arm64 Python in ./.venv):
#   uv venv --python 3.12 --python-preference only-managed .venv
#   uv pip install --python .venv/bin/python -r requirements-dev.txt
# Intel (x86_64 Python in ./.venv-x86_64, run through Rosetta on an Apple Silicon Mac). The deployment
# target makes the installer pick builds that run on macOS 10.15+ (e.g. pyscard's universal2 wheel,
# not its x86_64 one that needs macOS 15):
#   uv venv --python cpython-3.12-macos-x86_64 --python-preference only-managed .venv-x86_64
#   MACOSX_DEPLOYMENT_TARGET=10.15 uv pip install --python .venv-x86_64/bin/python \
#     --python-platform x86_64-apple-darwin -r requirements-dev.txt
set -e
cd "$(dirname "$0")"

case "${1:-arm64}" in
  all) "$0" arm64 && exec "$0" intel ;;
  arm64|apple-silicon) ARCH=arm64; PY=.venv/bin/python; RUN=(arch -arm64); OUT=dist; LABEL=apple-silicon; MIN_OS=11.0 ;;
  intel|x86_64) ARCH=x86_64; PY=.venv-x86_64/bin/python; RUN=(arch -x86_64); OUT=dist/intel; LABEL=intel; MIN_OS=10.15 ;;
  *) echo "Usage: $0 [arm64|intel|all]"; exit 1 ;;
esac

[ -x "$PY" ] || { echo "No $(dirname "$(dirname "$PY")") found - see the setup lines at the top of this script."; exit 1; }
[ "$("${RUN[@]}" "$PY" -c 'import platform; print(platform.machine())')" = "$ARCH" ] || { echo "$PY isn't $ARCH."; exit 1; }

"${RUN[@]}" "$PY" -m pytest -q -p no:cacheprovider || { echo "Tests failed ($ARCH) - not building."; exit 1; }

VERSION=$("$PY" -c 'import cfs_gui; print(cfs_gui.APP_VERSION)')
NAME=$("$PY" -c 'import cfs_gui; print(cfs_gui.APP_NAME)')
ICON=()  # the chosen app icon, once there is one (see branding/)
[ -f branding/Spoolhouse.icns ] && ICON=(--icon "$PWD/branding/Spoolhouse.icns")

"${RUN[@]}" "$PY" -m PyInstaller --noconfirm --clean --windowed --name "$NAME" \
  --target-arch "$ARCH" \
  --osx-bundle-identifier app.spoolhouse \
  --distpath "$OUT" --workpath "build_tmp/$ARCH" --specpath "build_tmp/$ARCH" --paths "$PWD" \
  --add-data "$PWD/web:web" "${ICON[@]}" \
  --collect-submodules webview --collect-submodules smartcard cfs_app.py

# stamp the version (and the oldest macOS it runs on) into Info.plist so Finder's Get Info shows it
PLIST="$OUT/$NAME.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string $MIN_OS" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion $MIN_OS" "$PLIST"
codesign --force --deep --sign - "$OUT/$NAME.app"  # re-seal after the plist edit (ad-hoc)
python3 tools/check_minos.py "$OUT/$NAME.app" "$MIN_OS" "$ARCH" || { echo "Not releasing: see above."; exit 1; }

rm -rf "build_tmp/$ARCH" "$OUT/$NAME"
rmdir build_tmp 2>/dev/null || true
ZIP="dist/$NAME-$VERSION-$LABEL.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$OUT/$NAME.app" "$ZIP"
echo "Built: $PWD/$OUT/$NAME.app ($VERSION, $ARCH, macOS $MIN_OS+)"
echo "Zip:   $PWD/$ZIP"

#!/bin/bash
# zeroconf (Phone access) has no ready-made Intel Mac build. Build it as plain Python (no compiled parts),
# then label it for macOS 10.15: its build tool otherwise labels it for the building Mac's macOS (e.g. 26),
# which the Intel app (macOS 10.15+) can't use. Then install it into the Intel environment.
#   tools/intel_zeroconf.sh .venv-x86_64/bin/python
set -e
PY=${1:?path to the Intel Python}
OUT=$(mktemp -d)
# the newest zeroconf that requirements.txt allows, from PyPI's own source package
VERSION=$(uv pip compile --quiet --python-platform x86_64-apple-darwin --python-version 3.12 requirements.txt \
          | grep -m1 '^zeroconf==' | cut -d= -f3)
SDIST=$(curl -fsS "https://pypi.org/pypi/zeroconf/$VERSION/json" \
        | python3 -c "import json,sys; print([f['url'] for f in json.load(sys.stdin)['urls'] if f['packagetype']=='sdist'][0])")
curl -fsSL -o "$OUT/zeroconf-$VERSION.tar.gz" "$SDIST"
SKIP_CYTHON=1 uv build --quiet --wheel --python "$PY" --out-dir "$OUT" "$OUT/zeroconf-$VERSION.tar.gz"
WHEEL=$(ls "$OUT"/zeroconf-*.whl)
if unzip -l "$WHEEL" | grep -qE '\.(so|pyd)$'; then echo "zeroconf wheel has compiled parts - refusing to relabel"; exit 1; fi
uv pip install --quiet --python "$PY" wheel
"$PY" -m wheel tags --remove --platform-tag macosx_10_15_x86_64 "$WHEEL" >/dev/null
uv pip install --quiet --python "$PY" --python-platform x86_64-apple-darwin "ifaddr>=0.1.7"
uv pip install --quiet --python "$PY" --no-deps "$OUT"/zeroconf-*macosx_10_15_x86_64.whl
echo "zeroconf $VERSION installed as plain Python, for macOS 10.15+"

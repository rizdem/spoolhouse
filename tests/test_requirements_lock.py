"""requirements.lock is what builds and tests install: it must agree with the minimums in requirements*.txt."""
import os
import re

import pytest
from packaging.requirements import Requirement

HERE = os.path.join(os.path.dirname(__file__), "..")

# the three kinds of computer the app is built for
ENVIRONMENTS = {
    "apple silicon": {"sys_platform": "darwin", "platform_machine": "arm64"},
    "intel mac": {"sys_platform": "darwin", "platform_machine": "x86_64"},
    "windows": {"sys_platform": "win32", "platform_machine": "AMD64"},
}


def read_requirements(name):
    """The requirement lines of a requirements file (following -r includes), without comments."""
    out = []
    for line in open(os.path.join(HERE, name), encoding="utf-8"):
        line = line.split("  #")[0].strip()
        if line.startswith("-r "):
            out += read_requirements(line[3:].strip())
        elif line and not line.startswith("#"):
            out.append(Requirement(line))
    return out


def read_lock():
    """requirements.lock's pinned lines: name==version with their marker, hashes and comments dropped."""
    out = []
    for line in open(os.path.join(HERE, "requirements.lock"), encoding="utf-8"):
        m = re.match(r"^([A-Za-z0-9_.\-]+==[^\s;\\]+)\s*(;[^\\]*)?\\?\s*$", line)
        if m:
            out.append(Requirement(m.group(1) + (m.group(2) or "")))
    return out


@pytest.mark.parametrize("env", ENVIRONMENTS)
def test_the_lock_meets_every_minimum(env):
    where = ENVIRONMENTS[env]
    locked = {}
    for r in read_lock():
        if r.marker is None or r.marker.evaluate(where):
            locked.setdefault(r.name.lower().replace("_", "-"), []).append(next(iter(r.specifier)).version)
    for req in read_requirements("requirements-dev.txt"):
        if req.marker is not None and not req.marker.evaluate(where):
            continue
        versions = locked.get(req.name.lower().replace("_", "-"))
        assert versions, f"{req.name} is wanted on {env} but isn't in requirements.lock: run tools/update_lock.sh"
        assert len(versions) == 1, f"{req.name} is locked to more than one version on {env}: {versions}"
        assert req.specifier.contains(versions[0], prereleases=True), \
            f"requirements.lock has {req.name} {versions[0]} on {env}, but the requirements say {req.specifier}: run tools/update_lock.sh"


def test_every_locked_package_has_hashes():
    text = open(os.path.join(HERE, "requirements.lock"), encoding="utf-8").read()
    blocks = re.split(r"\n(?=[A-Za-z0-9_.\-]+==)", text)
    pinned = [b for b in blocks if re.match(r"[A-Za-z0-9_.\-]+==", b)]
    assert pinned and all("--hash=sha256:" in b for b in pinned)

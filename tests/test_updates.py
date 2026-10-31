"""The update check: comparing versions, skipping, announcing once, and GitHub's answers."""
import io
import json
import urllib.error

import pytest

import updates


def release(v, url="https://github.com/rizdem/spoolhouse/releases/tag/v" ):
    return lambda current: {"version": v, "url": url + v, "published": "2026-11-02T10:00:00Z"}


def test_versions_compare_as_numbers():
    assert updates.parse_version("v2.10.0") > updates.parse_version("2.9.9")
    assert updates.parse_version("2.1") == (2, 1, 0)
    assert updates.parse_version("v2.1.0-beta") is None and updates.parse_version("") is None


def test_newer_release_is_offered():
    st = updates.check("2.0.3", fetch=release("2.1.0"))
    assert st["available"] and st["latest"]["version"] == "2.1.0" and st["problem"] is None


def test_same_or_older_release_is_not_offered():
    assert not updates.check("2.0.3", fetch=release("2.0.3"))["available"]
    assert not updates.check("2.0.3", fetch=release("1.9.0"))["available"]


def test_skipping_a_version_until_the_next_one():
    updates.check("2.0.3", fetch=release("2.1.0"))
    updates.skip("2.1.0")
    st = updates.status("2.0.3")
    assert not st["available"] and st["skipped"]
    assert updates.check("2.0.3", fetch=release("2.2.0"))["available"]


def test_announced_once_per_version():
    updates.check("2.0.3", fetch=release("2.1.0"))
    assert updates.should_notify("2.0.3")["version"] == "2.1.0"
    assert updates.should_notify("2.0.3") is None
    updates.check("2.0.3", fetch=release("2.1.1"))
    assert updates.should_notify("2.0.3")["version"] == "2.1.1"


def test_a_failed_check_keeps_what_was_known():
    updates.check("2.0.3", fetch=release("2.1.0"))
    def offline(current):
        raise IOError("Couldn't reach GitHub. Check your internet connection.")
    st = updates.check("2.0.3", fetch=offline)
    assert st["available"] and "internet" in st["problem"]


def test_daily_check_and_switching_it_off():
    assert updates.due()
    updates.check("2.0.3", fetch=release("2.0.3"))
    assert not updates.due()
    updates.set_auto(False)
    assert not updates.status("2.0.3")["auto"]


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_github_answer_is_read_and_links_kept_to_the_project(monkeypatch):
    body = {"tag_name": "v2.1.0", "html_url": "https://evil.example/download", "published_at": "2026-11-02T10:00:00Z"}
    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda req, timeout: FakeResponse(json.dumps(body).encode()))
    latest = updates.fetch_latest("2.0.3")
    assert latest["version"] == "2.1.0" and latest["url"] == updates.RELEASES_PAGE


@pytest.mark.parametrize("code, words", [(404, "No releases"), (403, "slow down"), (500, r"error \(500\)")])
def test_github_errors_are_readable(monkeypatch, code, words):
    def fail(req, timeout):
        raise urllib.error.HTTPError(updates.LATEST_URL, code, "x", {}, None)
    monkeypatch.setattr(updates.urllib.request, "urlopen", fail)
    with pytest.raises(IOError, match=words):
        updates.fetch_latest("2.0.3")


# ---------------------------------------------------------------- installing from inside the app
import hashlib
import os
import plistlib
import subprocess
import sys

BASE = "https://github.com/rizdem/spoolhouse/releases/download/v2.10.0/"


def asset(name, data, sha=None, url=None):
    return {"name": name, "url": url or BASE + name, "size": len(data), "sha256": sha or hashlib.sha256(data).hexdigest()}


class Body(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_latest_release_lists_its_files_with_their_fingerprints(monkeypatch):
    data = {"tag_name": "v2.10.0", "html_url": "https://github.com/rizdem/spoolhouse/releases/tag/v2.10.0", "assets": [
        {"name": "Spoolhouse-2.10.0-intel.zip", "browser_download_url": BASE + "Spoolhouse-2.10.0-intel.zip", "size": 5,
         "digest": "sha256:ABC123"},
        {"name": "evil.zip", "browser_download_url": "https://example.com/evil.zip", "size": 5, "digest": "sha256:00"}]}
    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda req, timeout: Body(json.dumps(data).encode()))
    latest = updates.fetch_latest("2.9.3")
    assert latest["assets"] == [{"name": "Spoolhouse-2.10.0-intel.zip", "url": BASE + "Spoolhouse-2.10.0-intel.zip",
                                 "size": 5, "sha256": "abc123"}]  # files from anywhere else are never offered


def test_each_computer_gets_its_own_download(monkeypatch):
    latest = {"assets": [asset(f"Spoolhouse-2.10.0{e}", b"x") for e in ("-apple-silicon.zip", "-intel.zip", "-windows-setup.exe")]}
    for computer, ending in updates.ENDINGS.items():
        monkeypatch.setattr(updates, "this_computer", lambda c=computer: c)
        assert updates.asset_for(latest)["name"].endswith(ending)


def test_a_download_is_only_kept_if_it_matches_github_exactly(tmp_path):
    data = b"the new app" * 1000
    good = asset("Spoolhouse-2.10.0-intel.zip", data)
    seen = []
    path = updates.download(good, str(tmp_path), lambda d, t: seen.append((d, t)), opener=lambda req, timeout: Body(data))
    assert open(path, "rb").read() == data and seen[-1] == (len(data), len(data))
    with pytest.raises(IOError, match="doesn't match"):  # changed on the way
        updates.download(good, str(tmp_path), opener=lambda req, timeout: Body(data[:-1] + b"!"))
    with pytest.raises(IOError, match="doesn't match"):  # cut short
        updates.download(good, str(tmp_path), opener=lambda req, timeout: Body(data[:100]))
    with pytest.raises(IOError, match="isn't from Spoolhouse"):
        updates.download(asset("x.zip", data, url="https://example.com/x.zip"), str(tmp_path), opener=lambda r, timeout: Body(data))


def test_running_from_source_never_installs_itself():
    latest = {"version": "9.9.9", "assets": [asset(f"Spoolhouse-9.9.9{e}", b"x") for e in updates.ENDINGS.values()]}
    assert not updates.installable(latest)  # the tests aren't a built app
    assert updates.status("2.9.3")["can_install"] is False


def test_windows_installs_into_the_same_folder_for_the_same_users(monkeypatch):
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    mine = updates.windows_helper(r"C:\T\setup.exe", r"C:\Users\r\AppData\Local\Programs\Spoolhouse\Spoolhouse.exe", 42, r"C:\T\log")
    shared = updates.windows_helper(r"C:\T\setup.exe", r"C:\Program Files\Spoolhouse\Spoolhouse.exe", 42, r"C:\T\log")
    assert "/CURRENTUSER" in mine and "/ALLUSERS" in shared
    folder = "C:\\Users\\r\\AppData\\Local\\Programs\\Spoolhouse"
    assert "Wait-Process -Id 42" in mine and "/SILENT" in mine
    assert "'/DIR=\"" + folder + "\"'" in mine  # into the folder it's in now
    assert "Start-Process -FilePath '" + folder + "\\Spoolhouse.exe'" in mine  # and opened again


mac_only = pytest.mark.skipif(sys.platform != "darwin", reason="Mac apps")


def fake_app(folder, version, marker):
    app = os.path.join(folder, "Spoolhouse.app")
    os.makedirs(os.path.join(app, "Contents", "MacOS"))
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleIdentifier": "app.spoolhouse", "CFBundleShortVersionString": version,
                       "CFBundleExecutable": "Spoolhouse", "CFBundlePackageType": "APPL"}, f)
    with open(os.path.join(app, "Contents", "MacOS", "Spoolhouse"), "w") as f:
        f.write(f"#!/bin/sh\n# {marker}\n")
    os.chmod(os.path.join(app, "Contents", "MacOS", "Spoolhouse"), 0o755)
    subprocess.run(["codesign", "-s", "-", "--force", app], check=True, capture_output=True)  # ad hoc, like our builds
    return app


@mac_only
def test_mac_unpacks_and_checks_the_new_app(tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    app = fake_app(str(src), "2.10.0", "new")
    zipped = str(tmp_path / "Spoolhouse-2.10.0-apple-silicon.zip")
    subprocess.run(["ditto", "-c", "-k", "--keepParent", app, zipped], check=True)
    os.makedirs(tmp_path / "a"), os.makedirs(tmp_path / "b")
    out = updates.unpack_mac(zipped, str(tmp_path / "a"), "2.10.0")
    assert out.endswith("Spoolhouse.app") and "new" in open(os.path.join(out, "Contents", "MacOS", "Spoolhouse")).read()
    with pytest.raises(IOError, match="expected version"):
        updates.unpack_mac(zipped, str(tmp_path / "b"), "2.10.1")


@mac_only
def test_mac_helper_swaps_the_app_once_it_has_quit_and_keeps_it_if_anything_fails(tmp_path):
    old = fake_app(str(tmp_path / "Applications"), "2.9.3", "old") if os.makedirs(tmp_path / "Applications") is None else None
    new = fake_app(str(tmp_path / "download"), "2.10.0", "new") if os.makedirs(tmp_path / "download") is None else None
    gone = subprocess.Popen(["true"])
    gone.wait()  # the app has quit
    script = tmp_path / "install.sh"
    script.write_text(updates.mac_helper(new, old, gone.pid, str(tmp_path / "update.log"), reopen=False))
    subprocess.run(["/bin/sh", str(script)], check=True, timeout=30)
    assert "new" in open(os.path.join(old, "Contents", "MacOS", "Spoolhouse")).read()
    assert not os.path.exists(new) and not os.path.exists(old + ".old-update")

    # a failed swap (the new app has gone missing) puts the old app back
    script.write_text(updates.mac_helper(str(tmp_path / "missing.app"), old, gone.pid, str(tmp_path / "update.log"), reopen=False))
    subprocess.run(["/bin/sh", str(script)], check=True, timeout=30)
    assert os.path.exists(os.path.join(old, "Contents", "Info.plist"))
    assert "putting the old app back" in (tmp_path / "update.log").read_text()


def test_force_offers_the_same_version_for_testing(monkeypatch):
    monkeypatch.setattr(updates, "FORCE", True)
    assert updates.check("2.10.0", fetch=release("2.10.0"))["available"]

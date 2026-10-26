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

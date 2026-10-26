"""The app's own logic (fit checks, auto-linking, alerts) and its local web server."""
import json
import threading
import urllib.error
import urllib.request

import pytest

import cfs_gui
import inventory as inv
from conftest import MATERIALS, mm_for


@pytest.fixture(autouse=True)
def clean_app_state(monkeypatch):
    cfs_gui.STATE.clear()
    cfs_gui._SENT.clear()
    monkeypatch.setattr(cfs_gui, "WATCH", {"low": None, "unassigned": None, "reader": None})
    sent = []
    monkeypatch.setitem(cfs_gui.NATIVE, "notify", lambda title, body: sent.append(title))
    yield sent
    cfs_gui.NATIVE.pop("notify", None)


def slot(local, material, color, mm, printing=False, tag=None, pid=1):
    return {"key": f"{pid}:{local}", "local": local, "present": True, "printing": printing, "material_code": material,
            "color": color, "remaining_mm": mm, "vendor": "Creality", "name": "", "type": "PLA", "tag": tag}


PLAN = [{"index": 0, "mm": 19892.67, "g": 59.81, "color": "FFFFFF", "type": "PLA", "vendor": "", "id": "00001"},
        {"index": 1, "mm": 334.76, "g": 1.01, "color": "FF0000", "type": "PLA", "vendor": "", "id": "00001"}]


def test_fit_check_short_and_enough(spool):
    p = inv.save_printer({"name": "K2", "model": "K2 Pro", "host": "x"})
    w = spool(total_g=500, remaining_g=40)
    inv.link_slot("1:1-0", w["id"], 87450, None, "01001|FFFFFF")
    slots = [slot("1-0", "01001", "FFFFFF", 87450), slot("1-1", "09001", "FF0000", 330000)]
    white, red = cfs_gui.fit_items(p, PLAN, slots)
    assert white["status"] == "short" and white["short_g"] == pytest.approx(19.3, abs=0.2)
    assert red["status"] == "ok" and red["source"] == "CFS estimate"


def test_fit_check_reserves_the_running_print(spool):
    p = inv.save_printer({"name": "K2", "model": "K2 Pro", "host": "x"})
    w = spool(total_g=500, remaining_g=100)
    inv.link_slot("1:1-0", w["id"], 87450, None, "01001|FFFFFF")
    slots = [slot("1-0", "01001", "FFFFFF", 87450)]
    item = cfs_gui.fit_items(p, PLAN[:1], slots, reserved={"1:1-0": mm_for(40)})[0]
    assert item["have_g"] == pytest.approx(60, abs=0.2)


def test_fit_check_finds_stock_for_unloaded_colours(spool):
    p = inv.save_printer({"name": "K2", "model": "K2 Pro", "host": "x"})
    petg = [{"index": 7, "mm": 57413.84, "g": 171.24, "color": "4C8D2B", "type": "PETG", "vendor": "", "id": "06001"}]
    spool(material="06001", color="00A651", remaining_g=493)
    item = cfs_gui.fit_items(p, petg, [slot("1-0", "01001", "FFFFFF", 87450)])[0]
    assert item["status"] == "unknown" and item["stock"]["found"] and item["stock"]["enough"]


def test_auto_link_by_tag(spool):
    p = inv.save_printer({"name": "K2", "model": "K2 Pro", "host": "x"})
    red = spool(material="09001", color="FF0000", serial="460882")
    s = slot("1-1", "09001", "FF0000", 330000, tag={"serial": "460882", "material": "09001", "color": "FF0000"})
    cfs_gui.auto_link(p, [s])
    assert inv.links()["1:1-1"]["spool_id"] == red["id"] and s["tag_match"] == red["id"]


def test_auto_link_respects_a_manual_unlink(spool):
    p = inv.save_printer({"name": "K2", "model": "K2 Pro", "host": "x"})
    spool(material="09001", color="FF0000", serial="460882")
    s = slot("1-1", "09001", "FF0000", 330000, tag={"serial": "460882", "material": "09001", "color": "FF0000"})
    cfs_gui.auto_link(p, [s])
    cfs_gui.pstate(1)["data"] = {"slots": [s], "boxes": []}
    cfs_gui.printer_link({"printer_id": 1, "slot_key": "1:1-1", "spool_id": None})
    cfs_gui.auto_link(p, [s])
    assert "1:1-1" not in inv.links()


def test_auto_link_asks_when_ambiguous_or_unknown(spool):
    p = inv.save_printer({"name": "K2", "model": "K2 Pro", "host": "x"})
    spool(serial="000001"); spool(serial="000001")
    twin = slot("1-0", "01001", "FFFFFF", 87450, tag={"serial": "000001", "material": "01001", "color": "FFFFFF"})
    stranger = slot("1-2", "06001", "FFFFFF", 1000, tag={"serial": "999999", "material": "06001", "color": "FFFFFF"})
    cfs_gui.auto_link(p, [twin, stranger])
    assert inv.links() == {}
    assert twin["tag_match"] == "several" and stranger["tag_match"] == "none"


def test_humidity_alert_once_until_it_recovers(clean_app_state):
    p = {"id": 1, "name": "K2"}
    highs = []
    for h in (36, 52, 55, 49, 51, 46, 53):
        data = {"boxes": [{"id": 1, "label": "CFS 1", "external": False, "humidity": h}], "slots": []}
        cfs_gui.check_humidity(p, data)
        highs.append(data["boxes"][0]["humid_high"])
    assert highs == [False, True, True, False, True, False, True]
    assert len(clean_app_state) == 2  # warned at 52 and again at 53 after dropping to 46


def test_low_stock_alert_only_on_change(spool, clean_app_state):
    s = spool(remaining_g=300)
    cfs_gui.watch_stock()
    assert clean_app_state == []  # nothing on start-up
    inv.save({**s, "remaining_g": 180})
    cfs_gui.watch_stock(); cfs_gui.watch_stock()
    assert clean_app_state == ["Running low"]


def test_notifications_can_be_switched_off(clean_app_state):
    inv.set_pref("notify_reader", "0")
    cfs_gui.notify("reader", "NFC reader unplugged", "")
    assert clean_app_state == []


# ---------------------------------------------------------------- the local web server
@pytest.fixture
def server():
    srv = cfs_gui.LocalServer(("127.0.0.1", 0), cfs_gui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def post(base, path, body=None, header=True):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(),
                                 headers={"X-CFS": "1"} if header else {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def test_page_and_files(server):
    html = urllib.request.urlopen(server + "/").read().decode()
    assert "window.CFS_CONFIG=" in html and f"js/core.js?v={cfs_gui.APP_VERSION}" in html and "__" not in html.split("<body>")[0]
    assert urllib.request.urlopen(server + "/js/core.js").status == 200
    for bad in ("/js/missing.js", "/../cfs_gui.py", "/js/../../inventory.py"):
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(server + bad)


def test_api_needs_the_page_header(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        post(server, "/api/inv/list", header=False)
    assert e.value.code == 403


def test_api_new_spools_need_a_tag(server):
    assert "Scan the spool" in post(server, "/api/inv/save", {"material": "01001", "total_g": 1000})["error"]
    saved = post(server, "/api/inv/save", {"material": "01001", "color": "FFFFFF", "total_g": 1000,
                                            "remaining_g": 1000, "serial": "123456", "uids": "AABBCCDD"})
    assert saved["spool"]["serial"] == "123456"
    assert len(post(server, "/api/inv/list")["spools"]) == 1


def test_fit_follows_the_printers_routing_for_a_running_print(spool):
    p = inv.save_printer({"name": "K2", "model": "K2 Pro", "host": "x"})
    white = spool(material="06001", color="FFFFFF", remaining_g=929)
    inv.link_slot("1:1-2", white["id"], 297000, None, "06001|FFFFFF")
    plan = [{"index": 0, "mm": 44000, "g": 133.3, "color": "7A92AC", "type": "PETG", "vendor": "", "id": "06001"}]
    slots = [slot("1-0", "01001", "FFFFFF", 87450), slot("1-2", "06001", "FFFFFF", 297000, printing=True)]
    item = cfs_gui.fit_items(p, plan, slots, routing={0: "1-2"})[0]
    assert item["slot_key"] == "1:1-2" and item["spool_id"] == white["id"]


def test_same_creality_material_matches_whatever_the_slicer_colour():
    f = {"index": 0, "mm": 1, "g": 1, "color": "7A92AC", "type": "PETG", "vendor": "", "id": "06001"}
    white = {"material": "06001", "color": "FFFFFF"}
    other_type = {"material": "01001", "color": "7A92AC"}
    assert cfs_gui.best_match(f, [other_type, white]) is white


def test_update_status_reaches_the_page_after_a_failed_check(server):
    # the page treats any reply with an "error" field as a failed request, so the last check's
    # problem must travel under another name
    import updates
    updates.check(cfs_gui.APP_VERSION, fetch=lambda v: {"version": "99.0.0", "url": updates.RELEASES_PAGE, "published": ""})
    def offline(v):
        raise IOError("Couldn't reach GitHub.")
    updates.check(cfs_gui.APP_VERSION, fetch=offline)
    st = post(server, "/api/update/status")
    assert "error" not in st and st["available"] and st["problem"] == "Couldn't reach GitHub."


def test_about_links_open_only_known_pages(server, monkeypatch):
    opened = []
    monkeypatch.setattr(cfs_gui.webbrowser, "open", opened.append)
    assert post(server, "/api/open", {"link": "source"})["ok"]
    assert not post(server, "/api/open", {"link": "https://evil.example"})["ok"]
    assert opened == ["https://github.com/rizdem/spoolhouse"]


def test_interface_scripts_never_declare_the_same_name_twice():
    # the page loads web/js/*.js as plain scripts sharing one scope: a second top-level `const x`
    # makes the browser drop that whole file (Phone access once vanished from Settings this way)
    import os
    import re
    html = open(os.path.join(cfs_gui.web_dir(), "index.html")).read()
    seen = {}
    for name in re.findall(r'src="js/([\w-]+\.js)', html):
        src = open(os.path.join(cfs_gui.web_dir(), "js", name)).read()
        for decl in re.findall(r"^(?:const|let|var|function|class|async function)\s+([A-Za-z_$][\w$]*)", src, re.M):
            assert decl not in seen, f"{decl} is declared in both {seen[decl]} and {name}"
            seen[decl] = name
    assert "loadPhone" in seen and "loadSettings" in seen

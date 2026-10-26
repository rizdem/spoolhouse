"""Phone access: pairing, the pinned certificate, and what a paired phone may (and may not) do."""
import hashlib
import json
import socket
import ssl
import urllib.parse

import pytest

import inventory as inv
import phone_access as pa


@pytest.fixture
def server():
    pa.start(port=0, host="127.0.0.1", announce=False)
    yield pa.STATE["server"].server_address[1]
    pa.stop()


def call(port, path, body=None, token=None, fingerprint=None):
    """Like the phone: HTTPS to the computer, trusting only the certificate in the QR code."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # checked by fingerprint below, as the phone does
    with socket.create_connection(("127.0.0.1", port), timeout=10) as raw, ctx.wrap_socket(raw) as s:
        der = s.getpeercert(binary_form=True)
        if fingerprint and hashlib.sha256(der).hexdigest().upper() != fingerprint:
            raise ssl.SSLError("certificate doesn't match the pairing QR code")
        data = json.dumps(body or {}).encode()
        head = (f"POST {path} HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(data)}\r\n" + (f"Authorization: Bearer {token}\r\n" if token else "")
                + "Connection: close\r\n\r\n")
        s.sendall(head.encode() + data)
        reply = b""
        while chunk := s.recv(65536):
            reply += chunk
    status = int(reply.split(b" ", 2)[1])
    return status, json.loads(reply.split(b"\r\n\r\n", 1)[1])


def pair(port, name="Test phone"):
    qr = pa.start_pairing()
    link = urllib.parse.parse_qs(urllib.parse.urlparse(qr["link"]).query)
    status, reply = call(port, "/api/phone/pair", {"code": link["c"][0], "name": name}, fingerprint=link["f"][0])
    assert status == 200
    return reply["token"], link


def test_off_by_default():
    assert not pa.enabled() and pa.STATE["server"] is None


def test_pairing_link_has_everything_the_phone_needs(server):
    qr = pa.start_pairing()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(qr["link"]).query)
    assert qr["link"].startswith("spoolhouse://pair?")
    assert len(q["c"][0]) == 6 and len(q["f"][0]) == 64 and q["p"] == [str(pa.PORT)]
    assert "127.0.0.1" not in q["h"][0].split(",") or q["h"] == ["127.0.0.1"]
    assert qr["qr_svg"].startswith("<svg")


def test_pair_then_use_the_inventory(server, spool):
    s = spool(serial="590267")
    token, link = pair(server)
    status, reply = call(server, "/api/inv/list", token=token, fingerprint=link["f"][0])
    assert status == 200 and [x["serial"] for x in reply["spools"]] == ["590267"]
    status, reply = call(server, "/api/inv/find", {"serial": "590267"}, token=token)
    assert reply["spool"]["id"] == s["id"]
    status, reply = call(server, "/api/phone/hello", token=token)
    assert reply["app"] == "Spoolhouse" and reply["phone"] == "Test phone"
    assert [p["name"] for p in inv.list_phones()] == ["Test phone"]


def test_codes_work_once_and_wrong_codes_are_refused(server):
    qr = pa.start_pairing()
    assert call(server, "/api/phone/pair", {"code": "000000" if qr["code"] != "000000" else "111111"})[0] == 403
    assert call(server, "/api/phone/pair", {"code": qr["code"], "name": "A"})[0] == 200
    assert call(server, "/api/phone/pair", {"code": qr["code"], "name": "B"})[0] == 403  # already used


def test_too_many_wrong_codes_cancels_pairing(server):
    qr = pa.start_pairing()
    for _ in range(pa.PAIR_TRIES):
        call(server, "/api/phone/pair", {"code": "x"})
    assert call(server, "/api/phone/pair", {"code": qr["code"]})[0] == 403


def test_unpaired_or_removed_phones_get_nothing(server):
    assert call(server, "/api/inv/list")[0] == 401
    assert call(server, "/api/inv/list", token="made-up")[0] == 401
    token, _ = pair(server)
    inv.remove_phone(inv.list_phones()[0]["id"])
    assert call(server, "/api/inv/list", token=token)[0] == 401


def test_phones_cannot_reach_the_reader_settings_or_backups(server):
    token, _ = pair(server)
    for path in ("/api/read", "/api/write", "/api/format", "/api/app/settings", "/api/backup/restore",
                 "/api/backup/save", "/api/export", "/api/phone/enable", "/api/phone/pair_start", "/api/open"):
        assert call(server, path, token=token)[0] == 403, path


def test_the_certificate_stays_the_same(server):
    fp = pa.status()["fingerprint"]
    pa.stop()
    pa.start(port=0, host="127.0.0.1", announce=False)
    assert pa.status()["fingerprint"] == fp  # phones paired earlier keep trusting it


def test_phone_updates_keep_what_they_leave_out(server, spool):
    s = spool(serial="590267", cost=11.99, source="Amazon", remaining_g=800)
    token, _ = pair(server)
    status, reply = call(server, "/api/inv/save", {"id": s["id"], "remaining_g": 640}, token=token)
    assert status == 200 and reply["spool"]["remaining_g"] == 640
    assert reply["spool"]["cost"] == 11.99 and reply["spool"]["source"] == "Amazon"  # not wiped


def test_phone_can_add_a_scanned_spool_but_not_twice(server):
    token, _ = pair(server)
    new = {"serial": "123456", "uids": "CA0B5CF8", "material": "01001", "color": "FFFDD0",
           "total_g": 1000, "remaining_g": 1000, "cost": 12.5, "source": "Creality Store", "purchased": "2026-10-26"}
    status, reply = call(server, "/api/inv/save", new, token=token)
    assert status == 200 and reply["spool"]["serial"] == "123456"
    assert "already in your inventory" in call(server, "/api/inv/save", new, token=token)[1]["error"]


def test_find_mentions_a_spool_in_recently_deleted(server, spool):
    s = spool(serial="777777")
    inv.delete(s["id"])
    token, _ = pair(server)
    reply = call(server, "/api/inv/find", {"serial": "777777"}, token=token)[1]
    assert reply["spool"] is None and reply["deleted_spool"]["id"] == s["id"]
    assert call(server, "/api/inv/restore", {"ids": [s["id"]]}, token=token)[0] == 200
    assert call(server, "/api/inv/find", {"serial": "777777"}, token=token)[1]["spool"]["id"] == s["id"]


def test_phone_picks_up_alerts_since_it_last_looked(server, monkeypatch):
    import cfs_gui
    token, _ = pair(server)
    first = call(server, "/api/phone/events", {}, token=token)[1]
    assert first["events"] == [] and "printing" in first   # a first look only learns where the log is up to
    cfs_gui.notify("print_done", "K2 Pro: print finished", "Bucket · 136 g of filament, about £1.65")
    cfs_gui.notify("low_stock", "Running low", "Creality Hyper PLA #FFFFFF: 180 g left.")
    cfs_gui.notify("reader", "NFC reader unplugged", "")   # desktop-only alerts aren't passed on
    got = call(server, "/api/phone/events", {"since": first["latest"]}, token=token)[1]
    assert [e["kind"] for e in got["events"]] == ["print_done", "low_stock"]
    assert got["events"][0]["title"] == "K2 Pro: print finished"
    again = call(server, "/api/phone/events", {"since": got["latest"]}, token=token)[1]
    assert again["events"] == []


def test_phone_alerts_are_logged_even_when_the_desktop_has_them_off():
    import cfs_gui
    inv.set_pref("notify_humidity", "0")
    cfs_gui.notify("humidity", "K2 Pro: CFS 1 is damp", "53% humidity")
    events, _ = inv.events_since(-1)
    assert [e["kind"] for e in events] == ["humidity"]


def test_a_weighing_made_offline_allows_for_printing_since(server, spool):
    import time as _t
    s = spool(serial="456095", remaining_g=900)
    token, _ = pair(server)
    weighed_at = _t.time() - 3600      # weighed an hour ago, away from home: 640 g
    with inv._db() as con:              # since then the printer used 25 g of it, and 10 g before the weighing
        con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job) VALUES (?, '', 0, 25, ?, 'j1')",
                    (s["id"], _t.time() - 600))
        con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job) VALUES (?, '', 0, 10, ?, 'j0')",
                    (s["id"], weighed_at - 600))
    reply = call(server, "/api/inv/save", {"id": s["id"], "remaining_g": 640, "measured_at": weighed_at}, token=token)[1]
    assert reply["spool"]["remaining_g"] == 615
    # without a time it's taken as it is (weighed just now)
    assert call(server, "/api/inv/save", {"id": s["id"], "remaining_g": 640}, token=token)[1]["spool"]["remaining_g"] == 640

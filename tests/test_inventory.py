"""Spools, deleting/restoring, serials, settings, shopping list and database migrations."""
import sqlite3
import time

import pytest

import inventory as inv
from conftest import MATERIALS, remaining


def test_save_cleans_values(spool):
    s = spool(color="#ff6b35", total_g="750", remaining_g="900.26", cost="12.345")
    assert s["color"] == "FF6B35"
    assert s["total_g"] == 750
    assert s["remaining_g"] == 750  # never more than the spool holds
    assert s["cost"] == 12.35


def test_grams_kept_to_a_tenth(spool):
    s = spool(remaining_g=321.27)
    assert s["remaining_g"] == 321.3


def test_update_keeps_id(spool):
    s = spool(remaining_g=500)
    s2 = inv.save({**s, "remaining_g": 420})
    assert s2["id"] == s["id"] and remaining(s["id"]) == 420


def test_delete_moves_to_recently_deleted_and_restore(spool):
    a, b = spool(), spool()
    inv.link_slot("1:1-0", a["id"], 1000, None, "01001|FFFFFF")
    inv.delete(a["id"])
    assert [s["id"] for s in inv.list_all()] == [b["id"]]
    assert [s["id"] for s in inv.deleted_spools()] == [a["id"]]
    assert "1:1-0" not in inv.links()  # out of the printer slot too
    assert inv.find_serial(a["serial"]) is None
    assert inv.find_serial(a["serial"], deleted=True)["id"] == a["id"]
    inv.restore([a["id"]])
    assert sorted(s["id"] for s in inv.list_all()) == sorted([a["id"], b["id"]])


def test_purge_after_30_days_and_on_request(spool):
    old, recent = spool(), spool()
    inv.delete_many([old["id"], recent["id"]])
    con = sqlite3.connect(inv.DB_PATH)
    con.execute("UPDATE spools SET deleted_at = ? WHERE id = ?", (time.time() - 31 * 86400, old["id"]))
    con.commit(); con.close()
    assert inv.purge_deleted() == 1
    assert [s["id"] for s in inv.deleted_spools()] == [recent["id"]]
    assert inv.purge_deleted([recent["id"]]) == 1
    assert inv.deleted_spools() == []


def test_purge_ignores_spools_not_in_the_bin(spool):
    s = spool()
    assert inv.purge_deleted([s["id"]]) == 0
    assert len(inv.list_all()) == 1


def test_new_serials_are_unique_and_skip_existing(spool, monkeypatch):
    spool(serial="555555")
    picks = iter([455555, 11111, 11111, 222222])  # -> 555555 (taken), 111111, 111111 (issued), 322222
    monkeypatch.setattr(inv.secrets, "randbelow", lambda n: next(picks))
    assert inv.new_serial() == "111111"
    assert inv.new_serial() == "322222"


def test_settings_defaults_and_updates():
    s = inv.get_settings()
    assert s["low_g"] == 250 and s["tare_g"] == 200 and s["humidity_max"] == 50
    assert inv.set_settings({"low_g": "300", "unknown": 5})["low_g"] == 300


def test_shopping_list(spool):
    low = spool(remaining_g=120, cost=12.99, source="Creality Store", purchased="2026-10-12")
    out = spool(material="00003", color="000000", remaining_g=0, cost=11.99, source="Amazon")
    plenty = spool(material="06001", color="00A651", remaining_g=800)
    items = {i["key"]: i for i in inv.shopping_list(MATERIALS)}
    assert items["01001|FFFFFF"]["reason"] == "low" and items["01001|FFFFFF"]["price"] == 12.99
    assert items["00003|000000"]["reason"] == "out"
    assert "06001|00A651" not in items
    inv.shopping_update("qty", "01001|FFFFFF", 3)
    inv.shopping_update("add", "06001|00A651")
    inv.shopping_update("hide", "00003|000000")
    items = {i["key"]: i for i in inv.shopping_list(MATERIALS)}
    assert items["01001|FFFFFF"]["qty"] == 3
    assert items["06001|00A651"]["reason"] == "added"
    assert items["00003|000000"]["hidden"]


def test_hidden_item_returns_when_it_runs_low_again(spool):
    s = spool(remaining_g=100)
    inv.shopping_update("hide", "01001|FFFFFF")
    inv.save({**s, "remaining_g": 900})  # restocked
    inv.shopping_list(MATERIALS)
    inv.save({**s, "remaining_g": 100})  # low again
    item = next(i for i in inv.shopping_list(MATERIALS) if i["key"] == "01001|FFFFFF")
    assert not item["hidden"]


def test_old_database_is_migrated(tmp_path):
    # a 1.0-era database: no brand/tare/deleted_at columns, one printer kept in prefs
    con = sqlite3.connect(inv.DB_PATH)
    con.execute("""CREATE TABLE spools (id INTEGER PRIMARY KEY AUTOINCREMENT, serial TEXT, material TEXT,
                   color TEXT, total_g INTEGER, remaining_g INTEGER, cost REAL, source TEXT, purchased TEXT,
                   notes TEXT, uids TEXT DEFAULT '', created REAL, updated REAL)""")
    con.execute("INSERT INTO spools (serial, material, color, total_g, remaining_g, updated) "
                "VALUES ('1','01001','FFFFFF',1000,500,0)")
    con.execute("CREATE TABLE prefs (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE slot_links (slot_key TEXT PRIMARY KEY, spool_id INTEGER, last_mm REAL, "
                "carry_g REAL DEFAULT 0, linked REAL)")
    con.executemany("INSERT INTO prefs VALUES (?, ?)", [("printer_host", "10.0.0.5"), ("track_job", "00000E")])
    con.execute("INSERT INTO slot_links VALUES ('1-0', 1, 87450, 0, 0)")
    con.commit(); con.close()

    spools = inv.list_all()
    assert spools[0]["remaining_g"] == 500 and spools[0]["brand"] == "" and spools[0]["deleted_at"] is None
    printers = inv.list_printers()
    assert len(printers) == 1 and printers[0]["host"] == "10.0.0.5" and printers[0]["track_job"] == "00000E"
    assert list(inv.links()) == [f"{printers[0]['id']}:1-0"]
    assert inv.get_pref("printer_host") == ""


def test_printer_crud():
    p = inv.save_printer({"name": "  Garage  ", "model": "Bambu", "host": "10.0.0.9"})
    assert p["name"] == "Garage" and p["model"] == "Other" and p["track_since"]
    p = inv.save_printer({"id": p["id"], "name": "Office", "model": "K2 Pro", "host": "10.0.0.9"})
    assert p["name"] == "Office" and p["model"] == "K2 Pro"
    inv.link_slot(f"{p['id']}:1-0", 1, 0)
    inv.delete_printer(p["id"])
    assert inv.list_printers() == [] and inv.links() == {}
    with pytest.raises(IOError):
        inv.get_printer(p["id"])


def test_data_carried_over_from_cfs_tag_writer(tmp_path, monkeypatch):
    # an old "CFS Tag Writer" folder with a spool in it
    old, new = tmp_path / "CFS Tag Writer", tmp_path / "Spoolhouse"
    old.mkdir(); (old / "Before restore").mkdir(); (old / "Before restore" / "safety.db").write_text("x")
    monkeypatch.setattr(inv, "DATA_DIR", str(old)); monkeypatch.setattr(inv, "DB_PATH", str(old / "inventory.db"))
    inv.save({"material": "01001", "color": "FFFFFF", "total_g": 1000, "remaining_g": 640, "serial": "1"})
    # first launch as Spoolhouse
    for name, value in (("OLD_DATA_DIR", str(old)), ("DEFAULT_DATA_DIR", str(new)), ("DATA_DIR", str(new)),
                        ("DB_PATH", str(new / "inventory.db"))):
        monkeypatch.setattr(inv, name, value)
    assert [s["remaining_g"] for s in inv.list_all()] == [640]
    assert (new / "Before restore" / "safety.db").exists()
    assert (old / "inventory.db").exists() and (old / "MOVED TO SPOOLHOUSE.txt").exists()  # old kept


def test_no_carry_over_into_a_custom_data_folder(tmp_path, monkeypatch):
    old = tmp_path / "CFS Tag Writer"; old.mkdir()
    monkeypatch.setattr(inv, "OLD_DATA_DIR", str(old))
    (old / "inventory.db").write_text("would be copied if this were the default folder")
    assert inv.list_all() == []  # the test's own (custom) folder stays empty

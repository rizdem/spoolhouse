"""Charging printer usage to spools: live charges, splits, refunds, costs and history."""
import sqlite3

import pytest

import inventory as inv
from conftest import MATERIALS, mm_for, remaining


def test_mm_to_grams():
    assert inv.mm_to_g(1000, "PLA") == pytest.approx(2.98, abs=0.01)
    assert inv.mm_to_g(330000, "PLA") == pytest.approx(984, abs=1)  # a 1 kg spool's tag length


def test_live_charge_on_a_linked_slot(spool):
    s = spool(remaining_g=300, cost=20)
    inv.link_slot("1:1-0", s["id"], 87450, None, "01001|FFFFFF")
    inv.charge("1:1-0", mm_for(10), "1:A", "PLA", MATERIALS)
    assert remaining(s["id"]) == 290
    u = inv.usage_for_job("1:A")[0]
    assert u["spool_id"] == s["id"] and u["color"] == "FFFFFF" and u["cost_g"] == pytest.approx(0.02)


def test_unlinked_slot_usage_is_unassigned_with_a_snapshot():
    inv.charge("1:1-1", mm_for(30), "1:A", "PLA", MATERIALS,
               slot={"material_code": "09001", "color": "FF0000", "vendor": "Creality"})
    u = inv.usage_for_job("1:A")[0]
    assert u["spool_id"] is None
    assert (u["material"], u["color"], u["brand"]) == ("09001", "FF0000", "Creality")


def test_split_charge_and_editing_refunds(spool):
    w, r = spool(remaining_g=500), spool(material="09001", color="FF0000", remaining_g=800)
    inv.set_job_charges("1:J", [{"spool_id": w["id"], "mm": mm_for(40)}, {"spool_id": r["id"], "mm": mm_for(20)}],
                        mm_for(60), MATERIALS)
    assert (remaining(w["id"]), remaining(r["id"])) == (460, 780)
    inv.set_job_charges("1:J", [{"spool_id": w["id"], "mm": mm_for(60)}], mm_for(60), MATERIALS)
    assert (remaining(w["id"]), remaining(r["id"])) == (440, 800)  # red refunded, never double-counted


def test_split_within_3_percent_counts_as_the_whole_print(spool):
    s = spool(material="00003", remaining_g=700)
    total = 57363.9
    short = inv.mm_to_g(total, "PLA") / inv.mm_to_g(1, "PETG")  # PLA grams typed for a PETG spool: 2.4% short
    inv.set_job_charges("1:J", [{"spool_id": s["id"], "mm": short}], total, MATERIALS)
    rows = inv.usage_for_job("1:J")
    assert len(rows) == 1 and rows[0]["mm"] == pytest.approx(total)


def test_partial_split_keeps_the_rest_unassigned(spool):
    a, b = spool(), spool(material="00003", color="000000")
    inv.set_job_charges("1:J", [{"spool_id": a["id"], "mm": 6000}, {"spool_id": b["id"], "mm": 3000}], 10000, MATERIALS)
    rows = inv.usage_for_job("1:J")
    assert [r["mm"] for r in rows if r["spool_id"] is None] == [pytest.approx(1000)]


def test_over_allocation_is_refused(spool):
    s = spool()
    with pytest.raises(IOError):
        inv.set_job_charges("1:J", [{"spool_id": s["id"], "mm": 2000}], 1000, MATERIALS)


def test_assign_unassigned_usage(spool):
    s = spool(material="09001", color="FF0000", remaining_g=1000)
    inv.charge("", mm_for(15), "1:B", "PLA", MATERIALS)
    u = inv.usage_for_job("1:B")[0]
    inv.assign_usage(u["id"], s["id"], MATERIALS)
    assert remaining(s["id"]) == pytest.approx(985, abs=0.1)
    with pytest.raises(IOError):
        inv.assign_usage(u["id"], s["id"], MATERIALS)


def test_past_print_charged_once(spool):
    s = spool()
    inv.add_job_usage("1:C", s["id"], mm_for(20), MATERIALS)
    with pytest.raises(IOError):
        inv.add_job_usage("1:C", s["id"], mm_for(20), MATERIALS)


def test_cost_follows_price_corrections_but_survives_deletion(spool):
    s = spool(total_g=500, remaining_g=400, cost=0)
    inv.set_job_charges("1:J", [{"spool_id": s["id"], "mm": mm_for(59.1)}], mm_for(59.1), MATERIALS)
    cost = lambda: round(sum(u["grams"] * u["cost_g"] for u in inv.usage_for_job("1:J")), 2)
    assert cost() == 0
    inv.save({**s, "remaining_g": 340.9, "cost": 12.99})
    assert cost() == 1.54
    inv.delete(s["id"]); inv.purge_deleted([s["id"]])
    assert cost() == 1.54


def test_monthly_totals(spool):
    w = spool(cost=20)
    r = spool(material="09001", color="FF0000")  # no price
    inv.set_job_charges("1:J1", [{"spool_id": w["id"], "mm": mm_for(60)}], mm_for(60), MATERIALS)
    inv.set_job_charges("1:J2", [{"spool_id": w["id"], "mm": mm_for(40)}, {"spool_id": r["id"], "mm": mm_for(20)}],
                        mm_for(60), MATERIALS)
    t = inv.usage_totals("1:", 0)
    assert t["prints"] == 2 and t["grams"] == pytest.approx(120) and t["cost"] == pytest.approx(2.0)
    assert t["unpriced_g"] == pytest.approx(20)


def test_skip_and_unskip(spool):
    inv.set_job_skipped("1:K", True)
    assert "1:K" in inv.skipped_jobs()
    inv.set_job_skipped("1:K", False)
    assert inv.skipped_jobs() == set()
    s = spool()
    inv.add_job_usage("1:L", s["id"], 1000, MATERIALS)
    with pytest.raises(IOError):
        inv.set_job_skipped("1:L", True)


def test_swap_detection(spool):
    s = spool()
    inv.link_slot("1:1-0", s["id"], 87450, None, "01001|FFFFFF")
    slot = {"key": "1:1-0", "present": True, "remaining_mm": 87450.0, "material_code": "01001", "color": "FFFFFF"}
    assert inv.check_swaps([slot]) == []
    assert inv.check_swaps([{**slot, "remaining_mm": None, "present": False}]) == []  # spool out: keep link
    assert inv.check_swaps([{**slot, "material_code": "09001", "color": "FF0000"}]) == ["1:1-0"]


def test_old_rounding_crumbs_are_folded_in(spool):
    s = spool(remaining_g=786)
    con = sqlite3.connect(inv.DB_PATH)
    con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job) VALUES (?, '', 2979, 9.1, 0, '1:Z')", (s["id"],))
    con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job) VALUES (NULL, '', 68, 0.21, 0, '1:Z')")
    con.execute("DELETE FROM prefs WHERE key = 'crumbs_folded'")
    con.commit(); con.close()
    inv.list_all()  # runs the one-off tidy-up
    rows = inv.usage_for_job("1:Z")
    assert len(rows) == 1 and rows[0]["mm"] == pytest.approx(3047)
    assert remaining(s["id"]) == pytest.approx(785.8, abs=0.05)


def test_live_charges_keep_one_row_per_print_slot_and_spool(spool):
    s = spool(remaining_g=900)
    inv.link_slot("1:1-2", s["id"], 297000, None, "06001|FFFFFF")
    for _ in range(5):  # five checks during one print
        inv.charge("1:1-2", 100, "1:F", "PETG", MATERIALS)
    rows = inv.usage_for_job("1:F")
    assert len(rows) == 1 and rows[0]["mm"] == pytest.approx(500)
    other = spool(material="09001", color="FF0000")
    inv.link_slot("1:1-1", other["id"], 330000, None, "09001|FF0000")
    inv.charge("1:1-1", 100, "1:F", "PLA", MATERIALS)  # colour change: a new row for the other slot
    assert len(inv.usage_for_job("1:F")) == 2


def test_old_split_up_rows_are_merged_once(spool):
    s = spool()
    con = sqlite3.connect(inv.DB_PATH)
    for i in range(4):
        con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job) VALUES (?, '1:1-2', 40, 0.12, ?, '1:F')",
                    (s["id"], i))
    con.execute("DELETE FROM prefs WHERE key = 'usage_merged'")
    con.commit(); con.close()
    inv.list_all()  # runs the one-off tidy-up
    rows = inv.usage_for_job("1:F")
    assert len(rows) == 1 and rows[0]["mm"] == pytest.approx(160) and rows[0]["grams"] == pytest.approx(0.48)

"""Projects: prints grouped together, with the filaments they used, their cost and print time."""
import pytest

import inventory as inv


def charge(job, spool_id, grams, color="FF0000", material="PLA", brand="Acme", cost_g=0.02):
    with inv._db() as con:
        con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job, color, material, brand, cost_g) "
                    "VALUES (?, 'k', ?, ?, 1, ?, ?, ?, ?, ?)", (spool_id, grams * 330, grams, job, color, material, brand, cost_g))


def printed(job, name="Part", duration=3600, start=1000):
    return {"job": job, "name": name, "printer": "K2", "status": "completed", "start": start, "duration": duration, "mm": 1000}


def test_a_project_adds_up_its_prints_filaments_time_and_cost():
    pid = inv.save_project("  Desk   tidy ")
    charge("1:a", 1, 100)                       # 100 g red, 2p a gram
    charge("1:a", 2, 50, color="000000", cost_g=None)  # 50 g black, no price
    charge("1:b", 1, 25)                        # 25 g more red
    charge("1:b", None, 10, color="000000")     # 10 g not assigned to a spool yet
    charge("1:c", 1, 999)                       # a print not in the project
    inv.add_to_project(pid, [printed("1:a", start=1000), printed("1:b", duration=1800, start=2000), printed("1:d", start=500)])

    p = inv.get_project(pid)
    assert p["name"] == "Desk tidy" and [x["job"] for x in p["prints"]] == ["1:b", "1:a", "1:d"]
    red, black = p["filaments"]
    assert (red["color"], red["grams"], red["cost"], red["prints"]) == ("FF0000", 125, 2.5, 2)
    assert (black["grams"], black["cost"], black["unpriced_g"]) == (50, None, 50)
    t = p["totals"]
    assert t["prints"] == 3 and t["duration"] == 3600 + 1800 + 3600
    assert t["grams"] == 185 and t["cost"] == 2.5 and t["unpriced_g"] == 50 and t["unassigned_g"] == 10
    assert t["uncharged"] == 1  # 1:d hasn't been charged to a spool
    a = next(x for x in p["prints"] if x["job"] == "1:a")
    assert a["cost"] == 2.0 and a["cost_partial"] and a["charged"]
    assert inv.list_projects()[0]["cost"] == 2.5


def test_a_print_is_in_one_project_at_most():
    one, two = inv.save_project("One"), inv.save_project("Two")
    inv.add_to_project(one, [printed("1:a")])
    inv.add_to_project(two, [printed("1:a")])  # moves it
    assert inv.get_project(one)["prints"] == [] and len(inv.get_project(two)["prints"]) == 1
    assert inv.project_of_jobs() == {"1:a": {"id": two, "name": "Two"}}


def test_removing_a_print_or_a_project_keeps_its_filament_charges():
    pid = inv.save_project("Gone")
    charge("1:a", 1, 100)
    inv.add_to_project(pid, [printed("1:a"), printed("1:b")])
    inv.remove_from_project("1:b")
    assert [x["job"] for x in inv.get_project(pid)["prints"]] == ["1:a"]
    inv.delete_project(pid)
    assert inv.list_projects() == [] and inv.project_of_jobs() == {}
    with inv._db() as con:
        assert con.execute("SELECT COUNT(*) FROM usage WHERE job = '1:a'").fetchone()[0] == 1


def test_a_project_needs_a_name_and_must_exist():
    with pytest.raises(ValueError, match="name"):
        inv.save_project("   ")
    with pytest.raises(ValueError, match="no longer exists"):
        inv.add_to_project(999, [printed("1:a")])
    pid = inv.save_project("Old")
    assert inv.save_project("New", "notes", pid) == pid and inv.get_project(pid)["name"] == "New"

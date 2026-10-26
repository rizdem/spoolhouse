"""Backups, restore, scheduled backups to a folder (e.g. a NAS) and CSV export."""
import os
import time

import pytest

import inventory as inv
from conftest import MATERIALS, remaining


def test_backup_and_restore(spool, tmp_path):
    s = spool(remaining_g=500)
    path = inv.backup_to(str(tmp_path / "manual.db"))
    assert inv.check_backup(path) == 1
    inv.save({**s, "remaining_g": 100})
    safety = inv.restore_from(path)
    assert remaining(s["id"]) == 500
    assert os.path.exists(safety)  # what was replaced is kept


def test_restore_refuses_other_files(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_text("not a database")
    with pytest.raises(IOError):
        inv.restore_from(str(junk))


def test_scheduled_backups_prune_only_their_own_files(spool, tmp_path):
    spool()
    nas = tmp_path / "nas"; nas.mkdir()
    (nas / "holiday-photos.txt").write_text("keep me")
    inv.set_backup_settings({"backup_dir": str(nas), "backup_freq": "daily", "backup_keep": 3})
    assert inv.run_scheduled_backup() is not None
    assert inv.run_scheduled_backup() is None  # not due again yet
    for _ in range(4):
        time.sleep(1.05)  # backups are named to the second
        inv.run_scheduled_backup(force=True)
    ours = [f for f in os.listdir(nas) if f.startswith(inv.BACKUP_PREFIX)]
    assert len(ours) == 3
    assert (nas / "holiday-photos.txt").exists()


def test_missing_folder_is_reported_not_fatal(spool):
    spool()
    inv.set_backup_settings({"backup_dir": "/Volumes/NoSuchNAS/backups", "backup_freq": "daily"})
    assert inv.run_scheduled_backup(force=True) is None
    assert "isn't available" in inv.backup_settings()["backup_error"]


def test_csv_exports(spool):
    s = spool(cost=20, source="Amazon")
    inv.charge("", 1000, "1:A", "PLA", MATERIALS)
    spools = inv.export_csv("spools", MATERIALS).splitlines()
    assert spools[0].startswith("Spool ID,Filament,Type")
    assert spools[1].startswith(f"{s['id']},Creality Hyper PLA,PLA")
    usage = inv.export_csv("usage", MATERIALS).splitlines()
    assert usage[0].startswith("Date,Printer,Print job") and "unassigned" in usage[1]
    with pytest.raises(IOError):
        inv.export_csv("nonsense", MATERIALS)

"""Shared test setup: every test gets its own empty database, and nothing touches the network,
the NFC reader or your real data."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cfs_tag  # noqa: E402
import inventory  # noqa: E402

MATERIALS = cfs_tag.MATERIALS


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Point the inventory at a new database in a temporary folder."""
    monkeypatch.setattr(inventory, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(inventory, "DB_PATH", str(tmp_path / "inventory.db"))
    yield tmp_path


@pytest.fixture
def spool():
    """Make a spool: spool(material="01001", color="FFFFFF", remaining_g=500, ...)."""
    counter = iter(range(100000, 999999))

    def make(**kw):
        rec = {"material": "01001", "color": "FFFFFF", "total_g": 1000, "remaining_g": 1000,
               "serial": str(next(counter))}
        rec.update(kw)
        return inventory.save(rec)
    return make


def mm_for(grams, type_name="PLA"):
    """Filament length that weighs `grams` for a material type."""
    return grams / inventory.mm_to_g(1, type_name)


def remaining(spool_id):
    return next(s["remaining_g"] for s in inventory.list_all() if s["id"] == spool_id)

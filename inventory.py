"""
inventory.py - local filament stock records (SQLite, no account, no internet).

A spool is identified by the serial written to its tags (both tags of a spool share it),
so scanning either tag finds the same record.

Data lives outside the app bundle so rebuilding the app never touches it:
    ~/Library/Application Support/Spoolhouse/inventory.db   (macOS)
    %APPDATA%\\Spoolhouse\\inventory.db                     (Windows)
(set SPOOLHOUSE_DATA_DIR to put it somewhere else). Data from before the rename (the app was called
CFS Tag Writer) is copied over on first launch; the old folder is left as it was.
"""
import contextlib
import csv
import datetime
import glob
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import sys
import threading
import time

def _default_data_dir():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming"), "Spoolhouse")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Spoolhouse")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "Spoolhouse")


DEFAULT_DATA_DIR = _default_data_dir()
OLD_DATA_DIR = os.path.expanduser("~/Library/Application Support/CFS Tag Writer")  # before 2.0
DATA_DIR = os.environ.get("SPOOLHOUSE_DATA_DIR") or os.environ.get("CFS_DATA_DIR") or DEFAULT_DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "inventory.db")

GRAMS = {"1kg": 1000, "750g": 750, "600g": 600, "500g": 500, "250g": 250}

FIELDS = ("serial", "material", "color", "total_g", "remaining_g", "cost", "source",
          "purchased", "notes", "uids", "tare_g", "brand")

# base plastic for Creality's own product lines (Generic materials are named after their type)
CREALITY_TYPE = {
    "01001": "PLA", "01601": "PLA", "02001": "PLA-CF", "03001": "ABS", "04001": "PLA",
    "05001": "PLA-Silk", "06001": "PETG", "06002": "PETG", "07001": "ABS", "07002": "PC",
    "08001": "PLA", "09001": "PLA", "09002": "PLA", "10001": "TPU", "11001": "PA",
    "12002": "PPA-CF", "12003": "PAHT-CF", "13001": "PLA-CF", "14001": "PLA", "15001": "PLA",
    "16001": "TPU", "17001": "PLA", "18001": "PLA", "19001": "ASA",
}

# g/cm3, typical values; used to turn the printer's filament length into grams
DENSITY = {
    "PLA": 1.24, "PLA-Silk": 1.24, "PLA-CF": 1.29, "PETG": 1.27, "PETG-CF": 1.30, "PETG-GF": 1.38,
    "PET": 1.38, "PET-CF": 1.35, "PCTG": 1.23, "ABS": 1.04, "ASA": 1.07, "ASA-CF": 1.12,
    "TPU": 1.21, "TPU 64D": 1.21, "PA": 1.14, "PA-CF": 1.20, "PA6-CF": 1.20, "PAHT-CF": 1.25,
    "PPA-CF": 1.25, "PC": 1.20, "PVA": 1.23, "BVOH": 1.14, "HIPS": 1.04, "PP": 0.90,
    "PPS": 1.35, "PPS-CF": 1.40,
}
FILAMENT_AREA_MM2 = 3.14159265 * (1.75 / 2) ** 2


def type_of(material_code, materials):
    """'PLA', 'PETG'... for a 5-digit material code, using the tag tool's MATERIALS names."""
    if material_code in CREALITY_TYPE:
        return CREALITY_TYPE[material_code]
    name = materials.get(material_code, "")
    return name.replace("Generic ", "").replace("Creality ", "") or "PLA"


def mm_to_g(mm, type_name):
    return mm * FILAMENT_AREA_MM2 / 1000 * DENSITY.get(type_name, 1.24)


DEFAULT_SETTINGS = {
    "low_g": 250,   # alert when a material+colour has less than this left across all its spools
    "tare_g": 200,  # default empty-spool weight for "weigh it" (weigh an empty one to get yours)
    "humidity_max": 50,  # warn when a CFS unit's humidity goes above this (%)
}

_lock = threading.Lock()  # one writer at a time; requests arrive on several threads


@contextlib.contextmanager
def _db():
    """Locked connection: commits on success, rolls back on error, always closes."""
    with _lock:
        con = _connect()
        try:
            with con:
                yield con
        finally:
            con.close()


def _carry_over_old_data():
    """First launch as Spoolhouse: copy the data from the CFS Tag Writer folder. A copy, not a move,
    so the old folder stays as a backup."""
    if DATA_DIR != DEFAULT_DATA_DIR or os.path.exists(DB_PATH):
        return
    old_db = os.path.join(OLD_DATA_DIR, "inventory.db")
    if not os.path.exists(old_db):
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    src, dst = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True), sqlite3.connect(DB_PATH)
    try:
        src.backup(dst)  # consistent even if the old app is still running
    finally:
        src.close(); dst.close()
    for name in os.listdir(OLD_DATA_DIR):  # e.g. "Before restore" safety copies
        path = os.path.join(OLD_DATA_DIR, name)
        if os.path.isdir(path):
            shutil.copytree(path, os.path.join(DATA_DIR, name), dirs_exist_ok=True)
    with open(os.path.join(OLD_DATA_DIR, "MOVED TO SPOOLHOUSE.txt"), "w") as f:
        f.write(f"This app is now called Spoolhouse. Your data was copied to:\n{DATA_DIR}\n"
                "This folder is kept as a backup and is no longer used. You can delete it once you're happy.\n")


def _connect():
    _carry_over_old_data()
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS spools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        serial TEXT, material TEXT, color TEXT,
        total_g INTEGER, remaining_g INTEGER,
        cost REAL, source TEXT, purchased TEXT, notes TEXT,
        uids TEXT DEFAULT '',
        created REAL, updated REAL)""")
    con.execute("CREATE INDEX IF NOT EXISTS spools_serial ON spools(serial)")
    # columns added after the first release - add them to existing databases
    cols = {r[1] for r in con.execute("PRAGMA table_info(spools)")}
    if "tare_g" not in cols:
        con.execute("ALTER TABLE spools ADD COLUMN tare_g INTEGER")
    if "brand" not in cols:
        con.execute("ALTER TABLE spools ADD COLUMN brand TEXT DEFAULT ''")
    if "deleted_at" not in cols:  # set when deleted; the spool sits in "Recently deleted" for 30 days
        con.execute("ALTER TABLE spools ADD COLUMN deleted_at REAL")
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    # every serial ever handed out for writing, so a spool written but never added to stock
    # still can't have its serial reused
    con.execute("CREATE TABLE IF NOT EXISTS serials (serial TEXT PRIMARY KEY, issued REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT)")
    # which spool sits in which printer slot; last_mm is the slot's remaining length when last seen
    con.execute("""CREATE TABLE IF NOT EXISTS slot_links (
        slot_key TEXT PRIMARY KEY, spool_id INTEGER, last_mm REAL, carry_g REAL DEFAULT 0, linked REAL)""")
    # every automatic deduction, for the printer page and the print log
    con.execute("""CREATE TABLE IF NOT EXISTS usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT, spool_id INTEGER, slot_key TEXT,
        mm REAL, grams REAL, at REAL)""")
    ucols = {r[1] for r in con.execute("PRAGMA table_info(usage)")}
    if "job" not in ucols:  # the print job the usage belongs to; spool_id NULL = not assigned yet
        con.execute("ALTER TABLE usage ADD COLUMN job TEXT")
        con.execute("ALTER TABLE usage ADD COLUMN type TEXT")
    if "color" not in ucols:
        # what the filament was at the time, so history survives spools being edited or deleted
        for col in ("color", "material", "brand", "label"):
            con.execute(f"ALTER TABLE usage ADD COLUMN {col} TEXT")
        con.execute("""UPDATE usage SET color = (SELECT color FROM spools WHERE spools.id = usage.spool_id),
                       material = (SELECT material FROM spools WHERE spools.id = usage.spool_id),
                       brand = (SELECT brand FROM spools WHERE spools.id = usage.spool_id)
                       WHERE spool_id IS NOT NULL""")
    con.execute("CREATE TABLE IF NOT EXISTS job_flags (job TEXT PRIMARY KEY, skipped INTEGER DEFAULT 0, at REAL)")
    # alerts for paired phones to pick up (print finished, running low, ...), the last week only
    con.execute("""CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL,
                   kind TEXT, title TEXT, body TEXT)""")
    # phones paired with Phone access: only a hash of each phone's token is kept
    con.execute("""CREATE TABLE IF NOT EXISTS phones (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
                   token_hash TEXT UNIQUE, created REAL, last_seen REAL)""")
    if "cost_g" not in {r[1] for r in con.execute("PRAGMA table_info(usage)")}:
        # the spool's price per gram when the filament was used, so a print's cost never changes later
        con.execute("ALTER TABLE usage ADD COLUMN cost_g REAL")
        con.execute("""UPDATE usage SET cost_g = (SELECT cost / total_g FROM spools
                       WHERE spools.id = usage.spool_id AND cost IS NOT NULL AND total_g > 0)
                       WHERE spool_id IS NOT NULL""")
    if not con.execute("SELECT 1 FROM prefs WHERE key = 'usage_merged'").fetchone():
        _merge_usage_rows(con)
        con.execute("INSERT OR REPLACE INTO prefs (key, value) VALUES ('usage_merged', '1')")
    if not con.execute("SELECT 1 FROM prefs WHERE key = 'crumbs_folded'").fetchone():
        _fold_crumbs(con)
        con.execute("INSERT OR REPLACE INTO prefs (key, value) VALUES ('crumbs_folded', '1')")
    lcols = {r[1] for r in con.execute("PRAGMA table_info(slot_links)")}
    if "sig" not in lcols:  # material+colour of the spool when linked, to spot a swap
        con.execute("ALTER TABLE slot_links ADD COLUMN sig TEXT")
    # printers the app follows; per-printer job tracking lives on the row
    con.execute("""CREATE TABLE IF NOT EXISTS printers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, model TEXT, host TEXT,
        created REAL, track_since REAL, track_job TEXT, track_mm REAL DEFAULT 0, track_slot TEXT)""")
    _migrate_single_printer(con)
    return con


def _migrate_single_printer(con):
    """1.1/1.2 kept one printer in prefs with un-prefixed slot keys and job ids. Move it into the
    printers table as printer 1 and prefix its slot links and usage with '1:'."""
    host = con.execute("SELECT value FROM prefs WHERE key = 'printer_host'").fetchone()
    if not host or con.execute("SELECT 1 FROM printers").fetchone():
        return
    pref = dict(con.execute("SELECT key, value FROM prefs").fetchall())
    cur = con.execute(
        "INSERT INTO printers (name, model, host, created, track_since, track_job, track_mm, track_slot) "
        "VALUES (?, '', ?, ?, ?, ?, ?, ?)",
        ("My printer", host[0], time.time(), float(pref.get("track_since") or time.time()),
         pref.get("track_job") or "", float(pref.get("track_mm") or 0),
         f"{1}:{pref['track_slot']}" if pref.get("track_slot") else ""))
    pid = cur.lastrowid
    con.execute("UPDATE slot_links SET slot_key = ? || ':' || slot_key WHERE slot_key NOT LIKE '%:%'", (str(pid),))
    con.execute("UPDATE usage SET slot_key = ? || ':' || slot_key WHERE slot_key != '' AND slot_key NOT LIKE '%:%'", (str(pid),))
    con.execute("UPDATE usage SET job = ? || ':' || job WHERE job IS NOT NULL AND job NOT LIKE '%:%'", (str(pid),))
    con.execute("DELETE FROM prefs WHERE key IN ('printer_host', 'track_since', 'track_job', 'track_mm', 'track_slot')")


def _merge_usage_rows(con):
    """One-off tidy-up for 1.11.1 and earlier, which wrote a new usage row at every check during a print:
    collapse them into one row per print, slot and spool (totals are unchanged)."""
    groups = con.execute("""SELECT job, slot_key, spool_id, COUNT(*) n, SUM(mm), SUM(grams), MAX(at), MIN(id)
                            FROM usage WHERE job IS NOT NULL GROUP BY job, slot_key, spool_id HAVING n > 1""").fetchall()
    for job, slot_key, spool_id, _, mm, grams, at, keep in groups:
        con.execute("UPDATE usage SET mm = ?, grams = ?, at = ? WHERE id = ?", (mm, grams, at, keep))
        con.execute("DELETE FROM usage WHERE job = ? AND slot_key IS ? AND spool_id IS ? AND id != ?",
                    (job, slot_key, spool_id, keep))


def _fold_crumbs(con):
    """One-off tidy-up for charges made before 1.4.1: a print charged to spools could keep a sliver
    (a few % from density rounding) as unassigned usage. Give it to the charged spools in proportion."""
    jobs = [r[0] for r in con.execute("SELECT DISTINCT job FROM usage WHERE job IS NOT NULL AND spool_id IS NULL")]
    for job in jobs:
        rows = [dict(r) for r in con.execute("SELECT * FROM usage WHERE job = ?", (job,))]
        charged = [u for u in rows if u["spool_id"]]
        crumbs = [u for u in rows if not u["spool_id"]]
        c_mm, t_mm = sum(u["mm"] for u in crumbs), sum(u["mm"] for u in rows)
        if not charged or not t_mm or c_mm / t_mm >= 0.03:
            continue  # nothing charged, or a real unassigned share: leave it for the user
        a_mm = sum(u["mm"] for u in charged)
        for u in charged:
            extra_mm = c_mm * u["mm"] / a_mm
            extra_g = u["grams"] * extra_mm / u["mm"] if u["mm"] else 0
            con.execute("UPDATE usage SET mm = mm + ?, grams = grams + ? WHERE id = ?", (extra_mm, extra_g, u["id"]))
            con.execute("UPDATE spools SET remaining_g = MAX(0, ROUND(remaining_g - ?, 1)) WHERE id = ?",
                        (extra_g, u["spool_id"]))
        con.execute("DELETE FROM usage WHERE job = ? AND spool_id IS NULL", (job,))


def list_all():
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM spools WHERE deleted_at IS NULL ORDER BY updated DESC")]


def find_serial(serial, deleted=False):
    """The spool with this tag serial (or, with deleted=True, one in Recently deleted)."""
    if not serial:
        return None
    with _db() as con:
        r = con.execute(f"SELECT * FROM spools WHERE serial = ? AND deleted_at IS {'NOT ' if deleted else ''}NULL "
                        "ORDER BY updated DESC LIMIT 1", (serial,)).fetchone()
        return dict(r) if r else None


def _clean(rec):
    out = {k: rec.get(k) for k in FIELDS}
    for k in ("total_g", "remaining_g"):
        out[k] = max(0.0, round(float(out[k] or 0), 1))  # tracked to 0.1 g
    out["remaining_g"] = min(out["remaining_g"], out["total_g"] or out["remaining_g"])
    out["cost"] = round(float(out["cost"]), 2) if out["cost"] not in (None, "") else None
    out["tare_g"] = max(0, int(float(out["tare_g"]))) if out["tare_g"] not in (None, "") else None
    out["color"] = (out["color"] or "").lstrip("#").upper()[:6]
    for k in ("serial", "material", "source", "purchased", "notes", "uids", "brand"):
        out[k] = str(out[k] or "").strip()
    return out


def save(rec):
    """Insert (no id) or update (with id). Returns the stored record."""
    data, now = _clean(rec), time.time()
    with _db() as con:
        if rec.get("id"):
            sets = ", ".join(f"{k} = ?" for k in data)
            cur = con.execute(f"UPDATE spools SET {sets}, updated = ? WHERE id = ?",
                              (*data.values(), now, int(rec["id"])))
            if cur.rowcount == 0:
                raise IOError("That spool no longer exists.")
            sid = int(rec["id"])
            # a spool's price is what was paid for it, so an edit is a correction: re-cost its prints
            # (deleting the spool keeps them, from the snapshot)
            con.execute("UPDATE usage SET cost_g = ? WHERE spool_id = ?",
                        (data["cost"] / data["total_g"] if data["cost"] is not None and data["total_g"] else None, sid))
        else:
            cols = ", ".join(data)
            cur = con.execute(
                f"INSERT INTO spools ({cols}, created, updated) VALUES "
                f"({', '.join('?' * len(data))}, ?, ?)", (*data.values(), now, now))
            sid = cur.lastrowid
        return dict(con.execute("SELECT * FROM spools WHERE id = ?", (sid,)).fetchone())


TRASH_DAYS = 30


def delete(sid):
    return delete_many([sid])


def get_settings():
    with _db() as con:
        stored = dict(con.execute("SELECT key, value FROM settings").fetchall())
    return {k: int(float(stored.get(k, v))) for k, v in DEFAULT_SETTINGS.items()}


def set_settings(values):
    with _db() as con:
        for k, v in values.items():
            if k in DEFAULT_SETTINGS and v not in (None, ""):
                con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                            (k, str(max(0, int(float(v))))))
    return get_settings()


def new_serial():
    """A random 6-digit serial not used by any spool in stock or issued before."""
    with _db() as con:
        for _ in range(1000):
            serial = f"{secrets.randbelow(900000) + 100000:06d}"
            taken = con.execute("SELECT 1 FROM spools WHERE serial = ? UNION ALL "
                                "SELECT 1 FROM serials WHERE serial = ?", (serial, serial)).fetchone()
            if not taken:
                con.execute("INSERT INTO serials (serial, issued) VALUES (?, ?)", (serial, time.time()))
                return serial
    raise IOError("Couldn't find an unused serial number.")


def delete_many(ids):
    """Move spools to Recently deleted (and out of any printer slot). Undo with restore()."""
    ids = [int(i) for i in ids]
    now = time.time()
    with _db() as con:
        con.executemany("UPDATE spools SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", [(now, i) for i in ids])
        con.executemany("DELETE FROM slot_links WHERE spool_id = ?", [(i,) for i in ids])
    return len(ids)


def restore(ids):
    ids = [int(i) for i in ids]
    with _db() as con:
        con.executemany("UPDATE spools SET deleted_at = NULL WHERE id = ?", [(i,) for i in ids])
    return len(ids)


def deleted_spools():
    with _db() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM spools WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")]
    for r in rows:
        r["days_left"] = max(0, TRASH_DAYS - int((time.time() - r["deleted_at"]) // 86400))
    return rows


def purge_deleted(ids=None):
    """Delete for good: the given spools, or (no ids) anything in Recently deleted over 30 days.
    Usage history keeps its colour/material snapshot, so past prints still read correctly."""
    with _db() as con:
        if ids is None:
            cutoff = time.time() - TRASH_DAYS * 86400
            gone = [r[0] for r in con.execute("SELECT id FROM spools WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))]
        else:
            gone = [r[0] for r in con.execute(
                f"SELECT id FROM spools WHERE deleted_at IS NOT NULL AND id IN ({','.join('?' * len(ids))})",
                [int(i) for i in ids])] if ids else []
        con.executemany("DELETE FROM spools WHERE id = ?", [(i,) for i in gone])
    return len(gone)


# ---------------------------------------------------------------- text preferences
def get_pref(key, default=""):
    with _db() as con:
        r = con.execute("SELECT value FROM prefs WHERE key = ?", (key,)).fetchone()
    return r[0] if r else default


def set_pref(key, value):
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO prefs (key, value) VALUES (?, ?)", (key, str(value)))


# ---------------------------------------------------------------- events for phones
EVENT_DAYS = 7


def log_event(kind, title, body):
    now = time.time()
    with _db() as con:
        con.execute("INSERT INTO events (at, kind, title, body) VALUES (?, ?, ?, ?)", (now, kind, title, body))
        con.execute("DELETE FROM events WHERE at < ? OR id <= (SELECT MAX(id) - 200 FROM events)",
                    (now - EVENT_DAYS * 86400,))


def events_since(after_id):
    """Events after `after_id`, oldest first, and the newest id. With no `after_id` (a phone's first look),
    just the newest id, so a newly paired phone isn't flooded with old alerts."""
    with _db() as con:
        latest = con.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
        if after_id is None:
            return [], latest
        rows = con.execute("SELECT * FROM events WHERE id > ? ORDER BY id", (int(after_id),)).fetchall()
    return [dict(r) for r in rows], latest


# ---------------------------------------------------------------- paired phones
def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def add_phone(name):
    """Pair a phone: returns its token (shown to the phone once, never stored in the clear)."""
    token = secrets.token_urlsafe(32)
    with _db() as con:
        con.execute("INSERT INTO phones (name, token_hash, created, last_seen) VALUES (?, ?, ?, ?)",
                    ((name or "Phone").strip()[:60] or "Phone", _token_hash(token), time.time(), time.time()))
    return token


def phone_for_token(token):
    """The paired phone with this token (and note that it was seen), or None."""
    if not token:
        return None
    with _db() as con:
        r = con.execute("SELECT * FROM phones WHERE token_hash = ?", (_token_hash(token),)).fetchone()
        if r:
            con.execute("UPDATE phones SET last_seen = ? WHERE id = ?", (time.time(), r["id"]))
    return dict(r) if r else None


def list_phones():
    with _db() as con:
        return [{k: r[k] for k in ("id", "name", "created", "last_seen")}
                for r in con.execute("SELECT * FROM phones ORDER BY created")]


def remove_phone(phone_id):
    with _db() as con:
        con.execute("DELETE FROM phones WHERE id = ?", (int(phone_id),))


# ---------------------------------------------------------------- printer slots
def links():
    with _db() as con:
        return {r["slot_key"]: dict(r) for r in con.execute("SELECT * FROM slot_links")}


def slot_sig(slot):
    return f"{slot.get('material_code', '')}|{slot.get('color', '')}"


def link_slot(slot_key, spool_id, remaining_mm, set_remaining_g=None, sig=None):
    """Link a slot to a spool (spool_id None unlinks). Usage counts from the slot's current
    length, so nothing already used is charged to the new spool."""
    with _db() as con:
        con.execute("DELETE FROM slot_links WHERE slot_key = ?", (slot_key,))
        if spool_id:
            # a spool can only be in one slot at a time
            con.execute("DELETE FROM slot_links WHERE spool_id = ?", (int(spool_id),))
            con.execute("INSERT INTO slot_links (slot_key, spool_id, last_mm, carry_g, linked, sig) "
                        "VALUES (?, ?, ?, 0, ?, ?)", (slot_key, int(spool_id), remaining_mm, time.time(), sig))
            if set_remaining_g is not None:
                con.execute("UPDATE spools SET remaining_g = MIN(total_g, ?), updated = ? WHERE id = ?",
                            (max(0.0, round(set_remaining_g, 1)), time.time(), int(spool_id)))


SWAP_MM = 1000  # a slot's loaded length jumping UP by more than 1 m means a different spool went in


def check_swaps(slots):
    """Drop links whose slot now holds a different spool (other material/colour, or a fuller spool).
    The CFS doesn't count its remaining length down while printing, so that figure is only used
    to recognise a newly loaded spool. Returns the slot keys that were unlinked."""
    swapped, by_key = [], {s["key"]: s for s in slots}
    with _db() as con:
        for ln in [dict(r) for r in con.execute("SELECT * FROM slot_links")]:
            key = ln["slot_key"]
            if con.execute("SELECT 1 FROM spools WHERE id = ?", (ln["spool_id"],)).fetchone() is None:
                con.execute("DELETE FROM slot_links WHERE slot_key = ?", (key,))
                continue
            slot = by_key.get(key)
            if not slot or not slot.get("present"):
                continue  # spool out for now, or not reported: keep the link
            cur, last, sig = slot.get("remaining_mm"), ln["last_mm"], slot_sig(slot)
            changed = (ln["sig"] and ln["sig"] != sig) or (
                cur is not None and last is not None and cur - last > SWAP_MM)
            if changed:
                con.execute("DELETE FROM slot_links WHERE slot_key = ?", (key,))
                swapped.append(key)
            else:
                con.execute("UPDATE slot_links SET last_mm = ?, sig = COALESCE(sig, ?) WHERE slot_key = ?",
                            (cur, sig, key))
    return swapped


def _take(con, spool_id, grams, now=None):
    """Deduct grams from a spool, kept to 0.1 g and never below zero."""
    con.execute("UPDATE spools SET remaining_g = MAX(0, ROUND(remaining_g - ?, 1)), updated = ? WHERE id = ?",
                (grams, now or time.time(), spool_id))


def _give_back(con, spool_id, grams, now=None):
    con.execute("UPDATE spools SET remaining_g = MIN(total_g, ROUND(remaining_g + ?, 1)), updated = ? WHERE id = ?",
                (grams, now or time.time(), spool_id))


def _cost_g(sp):
    return sp["cost"] / sp["total_g"] if sp["cost"] is not None and sp["total_g"] else None


def _snap_spool(sp):
    return {"color": sp["color"], "material": sp["material"], "brand": sp["brand"] or "", "cost_g": _cost_g(sp)}


def _snap_slot(slot):
    if not slot:
        return {"color": None, "material": None, "brand": None}
    return {"color": slot.get("color") or None, "material": slot.get("material_code") or None,
            "brand": slot.get("vendor") or None}


def _insert_usage(con, spool_id, slot_key, mm, grams, job, type_name, snap, label=""):
    con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job, type, color, material, brand, label, cost_g) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (spool_id, slot_key or "", mm, grams, time.time(), job, type_name,
                 snap["color"], snap["material"], snap["brand"], label, snap.get("cost_g")))


def charge(slot_key, mm, job, fallback_type, materials, slot=None, label=""):
    """Record `mm` of filament used by print `job` from `slot_key`. If the slot is linked, the
    spool's remaining grams go down now; otherwise the usage waits, unassigned, in the print log."""
    if mm <= 0:
        return None
    now = time.time()
    with _db() as con:
        ln = con.execute("SELECT * FROM slot_links WHERE slot_key = ?", (slot_key,)).fetchone() if slot_key else None
        spool = con.execute("SELECT * FROM spools WHERE id = ?", (ln["spool_id"],)).fetchone() if ln else None
        type_name = type_of(spool["material"], materials) if spool else (fallback_type or "PLA")
        grams = mm_to_g(mm, type_name)
        if spool:
            _take(con, spool["id"], grams, now)
        if not spool and slot and slot.get("material_code"):
            type_name = type_of(slot["material_code"], materials)
            grams = mm_to_g(mm, type_name)
        sid = spool["id"] if spool else None
        # live tracking charges a little at every check: keep one running row per print, slot and spool
        last = con.execute("SELECT id, slot_key, spool_id FROM usage WHERE job = ? ORDER BY id DESC LIMIT 1",
                           (job,)).fetchone() if job else None
        if last and last["slot_key"] == (slot_key or "") and last["spool_id"] == sid:
            con.execute("UPDATE usage SET mm = mm + ?, grams = grams + ?, at = ? WHERE id = ?",
                        (mm, grams, time.time(), last["id"]))
        else:
            _insert_usage(con, sid, slot_key, mm, grams, job, type_name,
                          _snap_spool(spool) if spool else _snap_slot(slot), label)
        return {"spool_id": spool["id"] if spool else None, "grams": grams}


def assign_usage(usage_id, spool_id, materials):
    """Give an unassigned usage entry to a spool and take it off that spool's stock."""
    with _db() as con:
        u = con.execute("SELECT * FROM usage WHERE id = ?", (int(usage_id),)).fetchone()
        sp = con.execute("SELECT * FROM spools WHERE id = ? AND deleted_at IS NULL", (int(spool_id),)).fetchone()
        if u is None or sp is None:
            raise IOError("That usage entry or spool no longer exists.")
        if u["spool_id"]:
            raise IOError("That usage has already been assigned.")
        grams = mm_to_g(u["mm"], type_of(sp["material"], materials))
        con.execute("UPDATE usage SET spool_id = ?, grams = ?, type = ?, color = ?, material = ?, brand = ?, cost_g = ? "
                    "WHERE id = ?", (sp["id"], grams, type_of(sp["material"], materials), sp["color"], sp["material"],
                                     sp["brand"] or "", _cost_g(sp), u["id"]))
        _take(con, sp["id"], grams)


def jobs_with_usage():
    with _db() as con:
        return {r[0] for r in con.execute("SELECT DISTINCT job FROM usage WHERE job IS NOT NULL")}


def usage_for_job(job):
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM usage WHERE job = ? ORDER BY at", (str(job),))]


def usage_between(start, end):
    with _db() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM usage WHERE at >= ? AND at <= ? ORDER BY at", (start, end))]


def recent_usage(limit=15):
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM usage ORDER BY at DESC LIMIT ?", (int(limit),))]


def add_job_usage(job, spool_id, mm, materials):
    """Charge a whole past print (whose feeding slot wasn't recorded) to one spool."""
    with _db() as con:
        if con.execute("SELECT 1 FROM usage WHERE job = ?", (str(job),)).fetchone():
            raise IOError("That print has already been charged to a spool.")
        sp = con.execute("SELECT * FROM spools WHERE id = ? AND deleted_at IS NULL", (int(spool_id),)).fetchone()
        if sp is None:
            raise IOError("That spool no longer exists.")
        type_name = type_of(sp["material"], materials)
        grams = mm_to_g(mm, type_name)
        con.execute("INSERT INTO usage (spool_id, slot_key, mm, grams, at, job, type) VALUES (?, '', ?, ?, ?, ?, ?)",
                    (sp["id"], mm, grams, time.time(), str(job), type_name))
        _take(con, sp["id"], grams)
        return grams


# ---------------------------------------------------------------- printers
PRINTER_MODELS = ["K2", "K2 Pro", "K2 Plus", "Hi", "K1", "K1C", "K1 Max", "K1 SE", "Other"]


def list_printers():
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM printers ORDER BY created")]


def get_printer(pid):
    with _db() as con:
        r = con.execute("SELECT * FROM printers WHERE id = ?", (int(pid),)).fetchone()
    if r is None:
        raise IOError("That printer no longer exists.")
    return dict(r)


def save_printer(rec):
    name = (rec.get("name") or "").strip()[:60] or "My printer"
    model = rec.get("model") if rec.get("model") in PRINTER_MODELS else "Other"
    host = (rec.get("host") or "").strip()
    with _db() as con:
        if rec.get("id"):
            cur = con.execute("UPDATE printers SET name = ?, model = ?, host = ? WHERE id = ?",
                              (name, model, host, int(rec["id"])))
            if cur.rowcount == 0:
                raise IOError("That printer no longer exists.")
            pid = int(rec["id"])
        else:
            # only prints from now on are tracked, not the printer's whole history
            pid = con.execute("INSERT INTO printers (name, model, host, created, track_since) VALUES (?, ?, ?, ?, ?)",
                              (name, model, host, time.time(), time.time())).lastrowid
        return dict(con.execute("SELECT * FROM printers WHERE id = ?", (pid,)).fetchone())


def delete_printer(pid):
    """Forget a printer and its slot links. Usage already charged to spools is kept."""
    with _db() as con:
        con.execute("DELETE FROM printers WHERE id = ?", (int(pid),))
        con.execute("DELETE FROM slot_links WHERE slot_key LIKE ?", (f"{int(pid)}:%",))


def set_tracking(pid, job="", mm=0.0, slot=""):
    with _db() as con:
        con.execute("UPDATE printers SET track_job = ?, track_mm = ?, track_slot = ? WHERE id = ?",
                    (job, float(mm), slot, int(pid)))


# ---------------------------------------------------------------- correcting a print's charges
def set_job_charges(job, allocations, total_mm, materials, label=""):
    """Replace everything charged for print `job` with `allocations` ([{spool_id, mm}]).
    Spools charged before get their grams back first, so editing never double-counts.
    Any length left over is kept as unassigned usage."""
    alloc_mm = sum(a["mm"] for a in allocations)
    if alloc_mm > total_mm * 1.03 + 1:
        raise IOError("That's more filament than the print used.")
    if allocations and alloc_mm >= total_mm * 0.97:
        # within 3% of the whole print counts as "all of it" (slicers and this app use slightly different
        # densities): scale the split to the exact total so no rounding crumbs are left unassigned
        allocations = [{**a, "mm": a["mm"] * total_mm / alloc_mm} for a in allocations]
        alloc_mm = total_mm
    now = time.time()
    with _db() as con:
        old = [dict(r) for r in con.execute("SELECT * FROM usage WHERE job = ?", (job,))]
        keep_label = label or next((u["label"] for u in old if u["label"]), "")
        for u in old:  # refund
            if u["spool_id"]:
                _give_back(con, u["spool_id"], u["grams"], now)
        con.execute("DELETE FROM usage WHERE job = ?", (job,))
        con.execute("DELETE FROM job_flags WHERE job = ?", (job,))
        for a in allocations:
            sp = con.execute("SELECT * FROM spools WHERE id = ? AND deleted_at IS NULL", (int(a["spool_id"]),)).fetchone()
            if sp is None:
                raise IOError("One of those spools no longer exists.")
            type_name = type_of(sp["material"], materials)
            grams = mm_to_g(a["mm"], type_name)
            _insert_usage(con, sp["id"], "", a["mm"], grams, job, type_name, _snap_spool(sp), keep_label)
            _take(con, sp["id"], grams, now)
        left = total_mm - alloc_mm
        if left > 50:  # more than 5 cm not given to a spool: keep it visible as unassigned
            snap = next(({"color": u["color"], "material": u["material"], "brand": u["brand"]}
                         for u in old if not u["spool_id"]), {"color": None, "material": None, "brand": None})
            first = allocations and con.execute("SELECT material FROM spools WHERE id = ?",
                                                (int(allocations[0]["spool_id"]),)).fetchone()
            type_name = type_of(first[0], materials) if first else (
                type_of(snap["material"], materials) if snap["material"] else "PLA")
            _insert_usage(con, None, "", left, mm_to_g(left, type_name), job, type_name, snap, keep_label)


def set_job_skipped(job, skipped):
    with _db() as con:
        if skipped:
            if con.execute("SELECT 1 FROM usage WHERE job = ? AND spool_id IS NOT NULL", (job,)).fetchone():
                raise IOError("That print is already charged to a spool. Edit its charges instead.")
            con.execute("DELETE FROM usage WHERE job = ?", (job,))  # drop any unassigned leftovers too
            con.execute("INSERT OR REPLACE INTO job_flags (job, skipped, at) VALUES (?, 1, ?)", (job, time.time()))
        else:
            con.execute("DELETE FROM job_flags WHERE job = ?", (job,))


def skipped_jobs():
    with _db() as con:
        return {r[0] for r in con.execute("SELECT job FROM job_flags WHERE skipped = 1")}


def usage_totals(job_prefix, since):
    """Grams and filament cost charged to spools for one printer's prints since a time."""
    with _db() as con:
        r = con.execute("SELECT COALESCE(SUM(grams), 0), SUM(grams * cost_g), COUNT(DISTINCT job), "
                        "SUM(CASE WHEN cost_g IS NULL THEN grams ELSE 0 END) FROM usage "
                        "WHERE spool_id IS NOT NULL AND job LIKE ? AND at >= ?", (job_prefix + "%", since)).fetchone()
    return {"grams": r[0], "cost": r[1], "prints": r[2], "unpriced_g": r[3] or 0}


# ---------------------------------------------------------------- backups
BACKUP_PREFIX = "Spoolhouse-backup-"
BACKUP_FREQS = {"off": None, "daily": 86400, "weekly": 7 * 86400}


def backup_name():
    return f"{BACKUP_PREFIX}{datetime.datetime.now():%Y-%m-%d-%H%M%S}.db"


def backup_to(path):
    """Write a consistent copy of the whole database to `path` (safe while the app is running)."""
    tmp = path + ".part"
    with _lock:
        src = _connect()
        try:
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    os.replace(tmp, path)  # only a complete file ever has the final name
    return path


def check_backup(path):
    """Raise IOError unless `path` is a readable Spoolhouse (or CFS Tag Writer) backup. Returns its spool count."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise IOError("That backup file is damaged.")
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='spools'").fetchone():
                raise IOError("That file isn't a Spoolhouse backup.")
            return con.execute("SELECT COUNT(*) FROM spools").fetchone()[0]
        finally:
            con.close()
    except sqlite3.DatabaseError:
        raise IOError("That file isn't a Spoolhouse backup.")


def restore_from(path):
    """Replace all data with a backup. The current data is saved first, next to the database."""
    check_backup(path)
    safety_dir = os.path.join(DATA_DIR, "Before restore")
    os.makedirs(safety_dir, exist_ok=True)
    safety = backup_to(os.path.join(safety_dir, backup_name()))
    with _lock:
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(DB_PATH)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    list_all()  # bring an older backup's tables up to date
    return safety


def backup_settings():
    keys = {"backup_dir": "", "backup_freq": "off", "backup_keep": "30", "backup_last": "0",
            "backup_last_file": "", "backup_error": "", "backup_tried": "0"}
    out = {k: get_pref(k, d) for k, d in keys.items()}
    out["backup_keep"] = int(out["backup_keep"])
    out["backup_last"] = float(out["backup_last"] or 0)
    out["backup_tried"] = float(out["backup_tried"] or 0)
    every = BACKUP_FREQS.get(out["backup_freq"])
    out["next_due"] = (out["backup_last"] + every) if every and out["backup_dir"] else None
    out["db_path"] = DB_PATH
    return out


def set_backup_settings(values):
    if "backup_dir" in values:
        set_pref("backup_dir", (values["backup_dir"] or "").strip())
        set_pref("backup_error", "")
    if values.get("backup_freq") in BACKUP_FREQS:
        set_pref("backup_freq", values["backup_freq"])
    if values.get("backup_keep"):
        set_pref("backup_keep", str(max(1, min(365, int(values["backup_keep"])))))
    return backup_settings()


def run_scheduled_backup(force=False):
    """Back up to the chosen folder when one is due. A missing folder (e.g. the NAS isn't connected)
    is recorded and tried again next time. Returns the file written, or None."""
    st = backup_settings()
    every = BACKUP_FREQS.get(st["backup_freq"])
    folder = st["backup_dir"]
    if not folder or (not every and not force):
        return None
    if not force and time.time() - st["backup_last"] < every:
        return None
    set_pref("backup_tried", time.time())
    if not os.path.isdir(folder):
        set_pref("backup_error", "The backup folder isn't available. If it's on a NAS, check it's connected.")
        return None
    try:
        path = backup_to(os.path.join(folder, backup_name()))
    except Exception as e:  # full disk, no permission, share dropped mid-write...
        set_pref("backup_error", f"Couldn't write the backup: {e}")
        return None
    set_pref("backup_last", time.time())
    set_pref("backup_last_file", path)
    set_pref("backup_error", "")
    # keep the newest N of our own backups in that folder; never touch anything else
    ours = sorted(glob.glob(os.path.join(folder, BACKUP_PREFIX + "*.db")))
    for old in ours[:-st["backup_keep"]]:
        try:
            os.remove(old)
        except OSError:
            pass
    return path


# ---------------------------------------------------------------- CSV export
def export_csv(kind, materials, color_name=lambda h: "#" + h):
    buf = io.StringIO()
    w = csv.writer(buf)
    if kind == "spools":
        w.writerow(["Spool ID", "Filament", "Type", "Brand", "Colour", "Hex", "Size (g)", "Remaining (g)", "Used (g)",
                    "Cost", "Cost per kg", "Shop", "Purchased", "Serial", "Tags", "Notes"])
        for s in list_all():
            per_kg = round(s["cost"] / s["total_g"] * 1000, 2) if s["cost"] is not None and s["total_g"] else ""
            w.writerow([s["id"], materials.get(s["material"], s["material"]), type_of(s["material"], materials),
                        s["brand"] or "", color_name(s["color"]), s["color"], s["total_g"], s["remaining_g"],
                        round(max(0, s["total_g"] - s["remaining_g"]), 1), "" if s["cost"] is None else s["cost"],
                        per_kg, s["source"], s["purchased"], s["serial"], s["uids"], s["notes"]])
    elif kind == "usage":
        names = {p["id"]: p["name"] for p in list_printers()}
        w.writerow(["Date", "Printer", "Print job", "Spool ID", "Filament", "Colour", "Hex", "Metres", "Grams", "Cost"])
        with _db() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM usage ORDER BY at")]
        for u in rows:
            pid, _, job = (u["job"] or "").partition(":")
            cost = round(u["grams"] * u["cost_g"], 2) if u["cost_g"] is not None and u["spool_id"] else ""
            w.writerow([datetime.datetime.fromtimestamp(u["at"]).strftime("%Y-%m-%d %H:%M"),
                        names.get(int(pid), f"Printer {pid}") if pid.isdigit() else "", job,
                        u["spool_id"] or "unassigned", materials.get(u["material"] or "", u["material"] or ""),
                        color_name(u["color"]) if u["color"] else "", u["color"] or "",
                        round(u["mm"] / 1000, 2), round(u["grams"], 1), cost])
    else:
        raise IOError("Unknown export.")
    return buf.getvalue()


# ---------------------------------------------------------------- shopping list
RECENT_OUT_DAYS = 60  # a filament you finished keeps showing as "out" for this long


def _shopping_state():
    try:
        st = json.loads(get_pref("shopping", "{}") or "{}")
    except ValueError:
        st = {}
    return {"qty": st.get("qty", {}), "extra": st.get("extra", []), "hidden": st.get("hidden", [])}


def _save_shopping(st):
    set_pref("shopping", json.dumps(st))


def filament_groups():
    """{'material|colour': {material, color, remaining, spools}} for every filament you have or had."""
    groups = {}
    for sp in list_all():
        key = f"{sp['material']}|{sp['color']}"
        g = groups.setdefault(key, {"key": key, "material": sp["material"], "color": sp["color"],
                                    "remaining": 0.0, "spools": []})
        g["remaining"] += sp["remaining_g"]
        g["spools"].append(sp)
    return groups


def shopping_list(materials):
    """What to buy: filaments running low or recently out, plus any you added; minus ones you hid.
    Each line carries the last price paid and where from."""
    low = get_settings()["low_g"]
    st = _shopping_state()
    groups = filament_groups()
    now = time.time()
    # a hidden filament comes back once it's been restocked and runs low again
    st["hidden"] = [k for k in st["hidden"] if k in groups and groups[k]["remaining"] < low]
    items = []
    for key, g in groups.items():
        recent = any(now - (sp["updated"] or 0) < RECENT_OUT_DAYS * 86400 for sp in g["spools"])
        is_low = 0 < g["remaining"] < low
        is_out = g["remaining"] <= 0 and recent
        if not (is_low or is_out or key in st["extra"]):
            continue
        newest = sorted(g["spools"], key=lambda sp: (sp["purchased"] or "", sp["created"] or 0), reverse=True)
        priced = next((sp for sp in newest if sp["cost"] is not None), None)
        items.append({
            "key": key, "material": g["material"], "color": g["color"],
            "name": materials.get(g["material"], g["material"]),
            "brand": next((sp["brand"] for sp in newest if sp["brand"]), ""),
            "size_g": newest[0]["total_g"], "remaining_g": round(g["remaining"], 1),
            "reason": "out" if g["remaining"] <= 0 else "low" if is_low else "added",
            "price": priced["cost"] if priced else None,
            "shop": next((sp["source"] for sp in newest if sp["source"]), ""),
            "bought": (priced or newest[0])["purchased"] or "",
            "qty": int(st["qty"].get(key, 1)), "hidden": key in st["hidden"],
        })
    items.sort(key=lambda i: (i["hidden"], i["remaining_g"]))
    _save_shopping(st)
    return items


def shopping_update(action, key, qty=None):
    st = _shopping_state()
    if action == "qty":
        st["qty"][key] = max(1, min(99, int(qty or 1)))
    elif action == "add" and key not in st["extra"]:
        st["extra"].append(key)
        if key in st["hidden"]:
            st["hidden"].remove(key)
    elif action == "hide":
        if key in st["extra"]:
            st["extra"].remove(key)  # something you added yourself is simply taken off
        elif key not in st["hidden"]:
            st["hidden"].append(key)
    elif action == "unhide" and key in st["hidden"]:
        st["hidden"].remove(key)
    _save_shopping(st)

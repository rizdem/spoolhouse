#!/usr/bin/env python3
"""
cfs_gui.py - the local server behind Spoolhouse (also runs on its own in a browser).

Keep this file in the same folder as cfs_tag.py, then:
    python3 -m pip install pyscard cryptography     (once)
    python3 cfs_gui.py

Your browser opens at http://127.0.0.1:8765. Ctrl+C in the Terminal to quit.
Quit SimplyPrint NFC Agent first so it isn't holding the reader.
"""
import json
import mimetypes
import os
import sys
import socketserver
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cfs_tag as cfs
import inventory as inv
import updates
import printer

PORT = 8765
APP_NAME = "Spoolhouse"
APP_VERSION = "2.3.0"
# Your Buy Me a Coffee (or Ko-fi / GitHub Sponsors) page. Leave empty to hide the Support button.
SUPPORT_URL = "https://buymeacoffee.com/rizdem"
# the only pages the About box can open (the page asks by name, never by URL)
LINKS = {
    "site": "https://spoolhouse.app",
    "source": "https://github.com/rizdem/spoolhouse",
    "issues": "https://github.com/rizdem/spoolhouse/issues",
    "licence": "https://github.com/rizdem/spoolhouse/blob/main/LICENSE",
    "credits": "https://github.com/DnG-Crafts/K2-RFID",
}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind() calls socket.getfqdn(), a reverse-DNS lookup that can
        # block for a long time (seen hanging inside a launched .app). We don't need it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


LOCK = threading.Lock()
CANCEL = threading.Event()
LOCK_TIMEOUT = 35  # seconds a request waits for the reader before giving up
on_error = lambda text: None  # noqa: E731 - cfs_app points this at its log file
NATIVE = {}  # filled in by cfs_app with things only the desktop app can do (menu bar/tray, login item, dialogs)
PLATFORM = "windows" if sys.platform == "win32" else "mac"


# ---------------------------------------------------------------- printers
SYNC_SECS = 60
FAST_SECS = 15  # while a print is running
STATE = {}      # printer id -> {"data", "job", "error", "at", "swapped", "logged_error"}
PRINTER_LOCK = threading.Lock()  # one fetch+sync at a time (background thread and page)


def pstate(pid):
    return STATE.setdefault(int(pid), {"data": None, "job": None, "error": None, "at": None,
                                       "swapped": set(), "logged_error": None, "fit": None})


def _prefixed(pid, data):
    """Slot keys are stored as '<printer id>:<box>-<slot>' so several printers can't collide."""
    for s in data["slots"]:
        s["local"], s["key"] = s["key"], f"{pid}:{s['key']}"
    return data


def printer_refresh(pid):
    """Read one printer, spot spool swaps, and charge linked spools for filament used."""
    p = inv.get_printer(pid)
    st = pstate(pid)
    with PRINTER_LOCK:
        try:
            data = _prefixed(pid, printer.fetch_slots(p["host"]))
        except IOError as e:
            st["error"] = str(e)
            if st["logged_error"] != str(e):  # log a new problem once, not every minute
                on_error(f"printer {p['name']}: {e}")
                st["logged_error"] = str(e)
            raise
        box = printer.fetch_box(p["host"])
        st["routing"] = printer.slot_routing(box)
        tags = printer.fetch_box_tags(p["host"], box)
        for s in data["slots"]:
            s["tag"] = tags.get(s["local"])
        auto_link(p, data["slots"])
        st["swapped"].update(k for k in inv.check_swaps(data["slots"])
                             if not any(s["key"] == k and s.get("tag_match") for s in data["slots"]))
        try:
            job = printer.fetch_job(p["host"])
        except IOError:
            job = None  # Moonraker unavailable: slots still show, usage waits until it's back
        if job:
            track_usage(p, job, data)
            catch_up(p)
        check_humidity(p, data)
        prev = (st.get("job") or {}).get("state")
        if job and prev in ("printing", "paused") and job["state"] in ("complete", "cancelled", "error"):
            print_finished(p, job)
        try:
            update_fit(p, data, job)
        except Exception as e:  # a fit check must never stop tracking
            on_error(f"fit check: {e}")
        st.update(data=data, job=job, error=None, at=time.time(), logged_error=None)
        return data


def _autolink_skips():
    try:
        return set(json.loads(inv.get_pref("autolink_skip", "[]") or "[]"))
    except ValueError:
        return set()


def _set_autolink_skip(key, on):
    skips = _autolink_skips()
    (skips.add if on else skips.discard)(key)
    inv.set_pref("autolink_skip", json.dumps(sorted(skips)))


def auto_link(p, slots):
    """Link each CFS slot to the spool whose tag the printer read: same serial, material and colour,
    and exactly one such spool (factory tags can share serials, so ambiguity is left to you). A slot
    you've unlinked or linked differently by hand is left alone for that spool."""
    links = inv.links()
    spools = inv.list_all()
    skips = _autolink_skips()
    for s in slots:
        tag = s.get("tag")
        s["tag_match"] = None
        if not s.get("present") or not tag:
            continue
        hits = [sp for sp in spools if sp["serial"] == tag["serial"] and sp["material"] == tag["material"]
                and (sp["color"] or "").upper() == tag["color"]]
        if len(hits) != 1:
            s["tag_match"] = "none" if not hits else "several"
            continue
        sp = hits[0]
        s["tag_match"] = sp["id"]
        ln = links.get(s["key"])
        if (ln and ln["spool_id"] == sp["id"]) or f"{s['key']}|{tag['serial']}" in skips:
            continue
        inv.link_slot(s["key"], sp["id"], s.get("remaining_mm"), None, inv.slot_sig(s))
        pstate(p["id"])["swapped"].discard(s["key"])
        links = inv.links()
        on_error(f"auto-linked {p['name']} {slot_label(s['local'])} to spool {sp['id']} (tag {tag['serial']})")


def track_usage(p, job, data):
    """Charge the filament used since the last check to the slot that is feeding right now.
    The CFS doesn't count a slot's length down while printing, so usage comes from Moonraker's
    running total for the job and the printer's 'selected' slot."""
    pid, host = p["id"], p["host"]
    t_job, t_mm, t_slot = p["track_job"] or "", float(p["track_mm"] or 0), p["track_slot"] or ""
    slots = data["slots"]
    active = next((s["key"] for s in slots if s.get("printing") and s.get("present")), "")
    if not active and data.get("no_cfs"):
        active = slots[0]["key"]  # one spool holder: it's always the one feeding
    by_key = {s["key"]: s for s in slots}
    running = job["state"] in ("printing", "paused") and job["job_status"] == "in_progress"
    if running:
        jid = str(job["job_id"])
        if t_job != jid:
            if t_job:
                finish_job(p, t_job, t_mm, t_slot)
            t_job, t_mm = jid, 0.0  # opened mid-print: what's used so far goes to the current slot
        delta = job["used_mm"] - t_mm
        slot = active or t_slot
        if delta > 0:
            inv.charge(slot, delta, f"{pid}:{t_job}", job["type_hint"], cfs.MATERIALS,
                       slot=by_key.get(slot), label=slot_label(slot.partition(":")[2]) if slot else "")
            t_mm = job["used_mm"]
        inv.set_tracking(pid, t_job, t_mm, slot)
    elif t_job:
        finish_job(p, t_job, t_mm, t_slot)


def finish_job(p, job_id, counted_mm, slot):
    """A tracked job has ended: charge whatever was used after the last check."""
    final = printer.job_total(p["host"], job_id)
    if final is not None and final > counted_mm:
        live = next((s for s in (pstate(p["id"])["data"] or {}).get("slots", []) if s["key"] == slot), None)
        inv.charge(slot, final - counted_mm, f"{p['id']}:{job_id}", "", cfs.MATERIALS,
                   slot=live, label=slot_label(slot.partition(":")[2]) if slot else "")
    inv.set_tracking(p["id"])


def catch_up(p):
    """Prints that ran start-to-finish while the app was closed: log them as unassigned usage
    (the slot that fed them is unknown) so they can be assigned to a spool in the print log."""
    since = float(p["track_since"] or 0)
    try:
        hist = printer.fetch_history(p["host"], limit=20)["jobs"]
    except IOError:
        return
    seen = inv.jobs_with_usage() | {f"{p['id']}:{p['track_job']}"}
    for j in hist:
        key = f"{p['id']}:{j['id']}"
        if j["status"] == "in_progress" or not j["end"] or j["end"] < since or key in seen:
            continue
        if j["mm"] > 0:
            inv.charge("", j["mm"], key, j["type_hint"], cfs.MATERIALS)


def _printer_loop():
    while True:
        busy = False
        for p in inv.list_printers():
            try:
                printer_refresh(p["id"])
            except Exception:
                pass
            busy |= (pstate(p["id"])["job"] or {}).get("state") in ("printing", "paused")
        # check often while printing so multi-colour jobs are split between slots accurately
        time.sleep(FAST_SECS if busy else SYNC_SECS)


def start_printer_sync():
    threading.Thread(target=_printer_loop, daemon=True).start()


# ---------------------------------------------------------------- notifications
NOTIFY_KINDS = [
    ("print_done", "Print finished", "When a print finishes or is cancelled, with the filament it used and its cost."),
    ("fit", "Filament may run out", "When a print needs more of a colour than its spool has left."),
    ("low_stock", "Running low", "When a filament drops below your low-stock limit."),
    ("to_charge", "Prints to charge", "When a print couldn't be charged to a spool automatically."),
    ("humidity", "CFS too damp", "When a CFS unit's humidity goes above your limit."),
    ("reader", "NFC reader", "When the reader is unplugged or plugged back in."),
    ("update", "Update available", "When a new version of Spoolhouse is out."),
]
_SENT = set()


def notify_enabled(kind):
    return inv.get_pref(f"notify_{kind}", "1") == "1"


def notify(kind, title, body):
    """Show a system notification (desktop app only), if that kind is switched on."""
    if not notify_enabled(kind) or "notify" not in NATIVE:
        return
    try:
        NATIVE["notify"](title, body)
    except Exception as e:
        on_error(f"notification: {e}")


def notify_once(kind, key, title, body):
    if key not in _SENT:
        _SENT.add(key)
        notify(kind, title, body)


def money(x):
    """Format an amount in the computer's own currency (falls back to a plain number)."""
    try:
        if sys.platform == "darwin":
            import Foundation
            f = Foundation.NSNumberFormatter.alloc().init()
            f.setNumberStyle_(Foundation.NSNumberFormatterCurrencyStyle)
            f.setLocale_(Foundation.NSLocale.currentLocale())
            return f.stringFromNumber_(round(x, 2))
        import locale
        locale.setlocale(locale.LC_MONETARY, "")  # the user's regional settings
        return locale.currency(round(x, 2), grouping=True)
    except Exception:
        return f"{x:.2f}"


def low_stock_groups():
    """{(material, colour): grams} for filaments below the low-stock limit (but not used up)."""
    low = inv.get_settings()["low_g"]
    groups = {}
    for s in inv.list_all():
        groups[(s["material"], s["color"])] = groups.get((s["material"], s["color"]), 0) + s["remaining_g"]
    return {k: v for k, v in groups.items() if 0 < v < low}


WATCH = {"low": None, "unassigned": None, "reader": None}


def _filament_name(material, color):
    return f"{cfs.MATERIALS.get(material, material).replace('Generic ', '')} #{color}"


def watch_stock():
    """Notify about filaments newly running low and new usage waiting to be charged."""
    low = low_stock_groups()
    if WATCH["low"] is not None:
        for k, g in low.items():
            if k not in WATCH["low"]:
                notify("low_stock", "Running low", f"{_filament_name(*k)}: {g:.0f} g left.")
    WATCH["low"] = set(low)
    n = sum(1 for u in inv.recent_usage(500) if not u["spool_id"])
    if WATCH["unassigned"] is not None and n > WATCH["unassigned"]:
        notify("to_charge", "A print needs charging",
               f"{n} usage entr{'ies' if n > 1 else 'y'} couldn't be charged to a spool. Open the print log to choose the spool.")
    WATCH["unassigned"] = n


def watch_reader():
    try:
        ok = bool(cfs._guard(cfs.readers))
    except Exception:
        ok = False
    if WATCH["reader"] is not None and ok != WATCH["reader"]:
        notify("reader", "NFC reader connected" if ok else "NFC reader unplugged",
               "Ready to scan and write tags." if ok else "Plug it back in to scan or write tags.")
    WATCH["reader"] = ok


def _watch_loop():
    tick = 0
    while True:
        try:
            watch_reader()
            if tick % 12 == 0:  # stock once a minute
                watch_stock()
            if tick % 720 == 0:  # once an hour: clear Recently deleted items older than 30 days
                inv.purge_deleted()
        except Exception as e:
            on_error(f"watch: {e}")
        tick += 1
        time.sleep(5)


def start_watchers():
    threading.Thread(target=_watch_loop, daemon=True).start()


def check_for_update(force=False):
    """Ask GitHub about a newer version (once a day, or now) and announce it once."""
    if force or updates.due():
        updates.check(APP_VERSION)
    latest = updates.should_notify(APP_VERSION)
    if latest:
        notify("update", f"{APP_NAME} {latest['version']} is available",
               f"You have {APP_VERSION}. Open {APP_NAME} to see what's new and download it.")
    return updates.status(APP_VERSION)


def _update_loop():
    time.sleep(60)  # let the app settle first
    while True:
        try:
            check_for_update()
        except Exception as e:
            on_error(f"update check: {e}")
        time.sleep(3600)  # check_for_update only asks GitHub once a day


def start_update_checker():
    threading.Thread(target=_update_loop, daemon=True).start()


def print_finished(p, job):
    """Called when a printer goes from printing to finished/cancelled."""
    key = f"{p['id']}:{job['job_id']}"
    rows = [u for u in inv.usage_for_job(key) if u["spool_id"]]
    grams = sum(u["grams"] for u in rows)
    cost = sum(u["grams"] * u["cost_g"] for u in rows if u["cost_g"] is not None)
    name = (job.get("filename") or "").rsplit(".", 1)[0].replace("_", " ")
    done = job["state"] == "complete"
    detail = f"{grams:.0f} g of filament" + (f", about {money(cost)}" if cost else "") if grams else "Filament not charged yet."
    notify_once("print_done", f"done:{key}", f"{p['name']}: print {'finished' if done else 'stopped'}",
                f"{name} · {detail}")


# ---------------------------------------------------------------- will it fit?
FIT_TIGHT = 1.10  # less than 10% to spare counts as tight


def _g_per_mm(material_code):
    return inv.mm_to_g(1, inv.type_of(material_code, cfs.MATERIALS)) if material_code else inv.mm_to_g(1, "PLA")


def best_match(f, candidates):
    """The candidate (slot or spool) most likely to be filament `f` from a print plan:
    same Creality material ID first, then same type, then the nearest colour."""
    ranked = all_matches(f, candidates)
    return ranked[0] if ranked else None


def all_matches(f, candidates):
    scored = []
    for c in candidates:
        code = c.get("material") or ""
        ctype = inv.type_of(code, cfs.MATERIALS).upper() if code else (c.get("type") or "").upper()
        if f["id"] and code == f["id"]:
            rank = 0
        elif f["type"] and ctype.startswith(f["type"].split("-")[0]):
            rank = 1
        else:
            continue
        dist = printer.color_distance(f["color"], (c.get("color") or "").upper())
        if rank > 0 and dist > 160:  # same type but a clearly different colour isn't this filament;
            continue                 # the same Creality material is, whatever colour the slicer showed
        scored.append((rank, dist, c))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [c for _, _, c in scored]


def stock_for(f, need_mm, exclude_id=None):
    """Spools in your inventory that could supply filament `f` (besides the one loaded), and whether
    they have enough for `need_mm`."""
    spools = [s for s in inv.list_all() if s["remaining_g"] > 0 and s["id"] != exclude_id]
    found = all_matches(f, [{"material": s["material"], "color": s["color"], "spool": s} for s in spools])
    if not found:
        return {"found": False}
    # the closest match decides which filament it is; gather every spool of that same filament
    top = found[0]["spool"]
    same = [c["spool"] for c in found if c["spool"]["material"] == top["material"] and c["spool"]["color"] == top["color"]]
    best = max(same, key=lambda s: s["remaining_g"])
    need_g = need_mm * _g_per_mm(top["material"])
    return {"found": True, "spool_id": best["id"], "material": top["material"], "color": top["color"],
            "brand": best["brand"] or "", "spools": len(same), "best_g": round(best["remaining_g"], 1),
            "total_g": round(sum(s["remaining_g"] for s in same), 1), "need_g": round(need_g, 1),
            "enough": best["remaining_g"] >= need_g}


def fit_items(p, plan, slots, job_key=None, reserved=None, routing=None):
    """For each filament in a print plan: the slot that will feed it, how much is still needed and
    how much the spool (or the CFS, if the slot isn't linked) has left. `reserved` ({slot key: mm}) is
    filament a running print still needs, so checking the next file answers "after this one"."""
    links = inv.links()
    spools = {s["id"]: s for s in inv.list_all()}
    used = {}
    for u in (inv.usage_for_job(job_key) if job_key else []):
        used[u["slot_key"]] = used.get(u["slot_key"], 0) + u["mm"]
    cands = [{"key": s["key"], "material": s["material_code"], "color": s["color"], "slot": s}
             for s in slots if s.get("present") and s.get("color")]
    items = []
    by_key = {c["key"]: c for c in cands}
    for f in plan or []:
        # a running print: the printer says which slot feeds each filament, so use that
        routed = (routing or {}).get(f["index"])
        m = by_key.get(f"{p['id']}:{routed}") if routed else None
        m = m or best_match(f, cands)
        item = {"color": f["color"], "type": f["type"], "plan_g": round(f["g"], 1), "status": "unknown"}
        if not m:
            item["note"] = "No matching filament is loaded"
            item["stock"] = stock_for(f, f["mm"])
            items.append(item)
            continue
        slot = m["slot"]
        ln = links.get(slot["key"])
        sp = spools.get(ln["spool_id"]) if ln else None
        need_mm = max(0.0, f["mm"] - used.get(slot["key"], 0))
        gpm = _g_per_mm(sp["material"] if sp else slot["material_code"])
        have_mm = (sp["remaining_g"] / gpm) if sp else slot.get("remaining_mm")
        if have_mm is not None and reserved:
            have_mm = max(0.0, have_mm - reserved.get(slot["key"], 0))
        item.update(slot_key=slot["key"], slot=slot_label(slot["key"].partition(":")[2]), need_mm=need_mm,
                    name=f"{slot.get('vendor', '')} {slot.get('name') or slot.get('type')}".strip(),
                    spool_id=sp["id"] if sp else None, need_g=round(need_mm * gpm, 1),
                    have_g=round(have_mm * gpm, 1) if have_mm is not None else None,
                    source="spool" if sp else "CFS estimate")
        if have_mm is None:
            item["status"] = "unknown"
        elif need_mm > have_mm:
            item["status"] = "short"
            item["short_g"] = round((need_mm - have_mm) * gpm, 1)
            item["stock"] = stock_for(f, need_mm, exclude_id=sp["id"] if sp else None)  # a spool to swap in?
        elif need_mm * FIT_TIGHT > have_mm:
            item["status"] = "tight"
        else:
            item["status"] = "ok"
        items.append(item)
    return items


HUMIDITY_RESET = 3  # must drop this far below the limit before it can warn again


def check_humidity(p, data):
    limit = inv.get_settings()["humidity_max"]
    st = pstate(p["id"])
    high = st.setdefault("humid", set())
    for b in data["boxes"]:
        if b["external"] or b.get("humidity") is None:
            continue
        b["humid_high"] = b["humidity"] > limit
        if b["humidity"] > limit and b["id"] not in high:
            high.add(b["id"])
            notify("humidity", f"{p['name']}: {b['label']} is damp",
                   f"Humidity is {b['humidity']:.0f}% (your limit is {limit}%). Dry the filament or check the desiccant.")
        elif b["humidity"] < limit - HUMIDITY_RESET:
            high.discard(b["id"])


def update_fit(p, data, job):
    """While printing, keep a fit check for the current file (and flag anything running short)."""
    st = pstate(p["id"])
    if not job or job["state"] not in ("printing", "paused") or job.get("job_status") != "in_progress":
        st["fit"] = None
        return
    plan = printer.fetch_plan(p["host"], job.get("filename"))
    items = fit_items(p, plan, data["slots"], f"{p['id']}:{job['job_id']}", routing=st.get("routing")) if plan else []
    st["fit"] = {"file": job.get("filename"), "items": items, "has_plan": bool(plan)}
    for it in items:
        if it["status"] == "short":
            notify_once("fit", f"fit:{p['id']}:{job['job_id']}:{it['color']}",
                        f"{p['name']}: filament may run out",
                        f"{it['name']} ({it['slot']}) needs about {it['need_g']:.0f} g more but has {it['have_g']:.0f} g.")


def job_plan(pid, filename):
    """A finished print's filament plan matched to your spools, for pre-filling its charges."""
    plan = printer.fetch_plan(inv.get_printer(pid)["host"], filename)
    if not plan:
        return {"filaments": []}
    links = inv.links()
    in_this = {ln["spool_id"] for k, ln in links.items() if k.startswith(f"{pid}:")}
    spools = [s for s in inv.list_all() if s["remaining_g"] > 0 or s["id"] in in_this]
    loaded = [{"material": s["material"], "color": s["color"], "spool": s} for s in spools if s["id"] in in_this]
    others = [{"material": s["material"], "color": s["color"], "spool": s} for s in spools if s["id"] not in in_this]
    out = []
    for f in plan:
        m = best_match(f, loaded) or best_match(f, others)
        out.append({"color": f["color"], "type": f["type"], "id": f["id"], "mm": f["mm"], "g": f["g"],
                    "spool_id": m["spool"]["id"] if m else None})
    return {"filaments": out}


def slot_label(local_key):
    box, slot = (local_key.split("-") + ["0"])[:2]
    return "External holder" if box == "0" else f"CFS {box} · Slot {int(slot) + 1}"


def _slot_view(s):
    ln = inv.links().get(s["key"])
    out = dict(s)
    out["spool_id"] = ln["spool_id"] if ln else None
    out["grams"] = (inv.mm_to_g(s["remaining_mm"], inv.type_of(s["material_code"], cfs.MATERIALS))
                    if s["remaining_mm"] is not None else None)
    return out


def printer_summary(p):
    """What the printers list needs: status, loaded colours, unlinked slots."""
    st = pstate(p["id"])
    slots = [_slot_view(s) for s in (st["data"] or {}).get("slots", [])]
    job = st["job"] or {}
    return {"id": p["id"], "name": p["name"], "model": p["model"], "host": p["host"],
            "online": st["at"] is not None and not st["error"], "error": st["error"], "at": st["at"],
            "state": job.get("state") or "", "used_mm": job.get("used_mm") or 0,
            "loaded": [{"color": s["color"], "printing": s["printing"]} for s in slots if s["present"] and s["color"]],
            "unlinked": sum(1 for s in slots if s["present"] and not s["spool_id"]),
            "fit_short": sum(1 for i in ((st.get("fit") or {}).get("items") or []) if i["status"] == "short"),
            "humid": [{"label": b["label"], "humidity": b["humidity"]} for b in (st["data"] or {}).get("boxes", [])
                      if b.get("humid_high")]}


def printer_detail(pid, refresh=True):
    p = inv.get_printer(pid)
    out = printer_summary(p)
    if refresh:
        try:
            printer_refresh(pid)
        except IOError as e:
            out["error"] = str(e)
        out = {**printer_summary(p), "error": out["error"] or pstate(pid)["error"]}
    st = pstate(pid)
    data = st["data"] or {"boxes": [], "slots": []}
    slots = [_slot_view(s) for s in data["slots"]]
    for s in slots:
        s["swapped"] = s["key"] in st["swapped"]
    usage = [u for u in inv.recent_usage(40) if u["job"] and u["job"].startswith(f"{pid}:")][:15]
    out.update(boxes=data["boxes"], slots=slots, no_cfs=bool(data.get("no_cfs")), usage=usage, fit=st.get("fit"),
               job=st["job"], sync_secs=SYNC_SECS, fast_secs=FAST_SECS)
    return out


def printer_link(body):
    pid, key, sid = int(body["printer_id"]), body["slot_key"], body.get("spool_id")
    slot = next((s for s in (pstate(pid)["data"] or {}).get("slots", []) if s["key"] == key), None)
    if slot is None:
        raise IOError("That slot isn't showing on the printer right now. Refresh and try again.")
    set_g = None
    if sid and body.get("use_printer_amount") and slot["remaining_mm"] is not None:
        spool = next((s for s in inv.list_all() if s["id"] == int(sid)), None)
        if spool:
            set_g = inv.mm_to_g(slot["remaining_mm"], inv.type_of(spool["material"], cfs.MATERIALS))
    inv.link_slot(key, sid, slot["remaining_mm"], set_g, inv.slot_sig(slot))
    pstate(pid)["swapped"].discard(key)
    tag = slot.get("tag")
    if tag:  # unlinking, or picking a different spool than the tag says, turns auto-linking off for it
        matched = sid and str(slot.get("tag_match")) == str(sid)
        _set_autolink_skip(f"{key}|{tag['serial']}", not matched)
    return printer_detail(pid, refresh=False)


def spools_in_printer():
    """{spool_id: {"slot": "<printer> · <slot>", "printing": bool}} for spools linked to a slot."""
    printers = {p["id"]: p for p in inv.list_printers()}
    out = {}
    for key, ln in inv.links().items():
        pid_s, _, local = key.partition(":")
        p = printers.get(int(pid_s)) if pid_s.isdigit() else None
        if not p:
            continue
        st = pstate(p["id"])
        live = next((s for s in (st["data"] or {}).get("slots", []) if s["key"] == key), {})
        running = (st["job"] or {}).get("state") in ("printing", "paused")
        out[ln["spool_id"]] = {"slot": f"{p['name']} · {slot_label(local)}",
                               "printing": running and bool(live.get("printing"))}
    return out


def printer_history(pid, limit=50, start=0):
    p = inv.get_printer(pid)
    hist = printer.fetch_history(p["host"], limit, start)
    spools = {s["id"]: s for s in inv.list_all()}
    skipped = inv.skipped_jobs()
    since = float(p["track_since"] or 0)
    for j in hist["jobs"]:
        key = f"{pid}:{j['id']}"
        rows = inv.usage_for_job(key)
        per = {}
        cost, unpriced = 0.0, False
        for u in rows:
            if u["spool_id"]:
                d = per.setdefault(u["spool_id"], {"spool_id": u["spool_id"], "grams": 0, "mm": 0,
                                                   "color": u["color"], "material": u["material"], "brand": u["brand"]})
                d["grams"] += u["grams"]; d["mm"] += u["mm"]
                if u["cost_g"] is None:
                    unpriced = True
                else:
                    cost += u["grams"] * u["cost_g"]
        for d in per.values():
            sp = spools.get(d["spool_id"])
            d["exists"] = sp is not None
            d["grams"] = round(d["grams"], 1)
        j["spools"] = list(per.values())
        j["unassigned"] = [{"usage_id": u["id"], "grams": round(u["grams"], 1), "mm": u["mm"],
                            "color": u["color"], "material": u["material"], "label": u["label"]}
                           for u in rows if not u["spool_id"]]
        first = spools.get(next(iter(per), None))
        type_name = inv.type_of(first["material"], cfs.MATERIALS) if first else (j["type_hint"] or "PLA")
        j["grams"] = round(inv.mm_to_g(j["mm"], type_name), 1)
        j["cost"] = round(cost, 2) if per and cost else None   # filament cost of what's been charged
        j["cost_partial"] = bool(per) and unpriced and cost > 0     # some spools have no price
        j["skipped"] = key in skipped
        j["tracked_era"] = bool(j["start"] and j["start"] >= since)
        j["needs"] = (j["status"] != "in_progress" and j["mm"] > 0 and not j["skipped"]
                      and (bool(j["unassigned"]) or not rows))
    import datetime
    month = datetime.date.today().replace(day=1)
    hist["month"] = inv.usage_totals(f"{pid}:", time.mktime(month.timetuple()))
    return hist


def job_charges(body):
    """Set which spools a finished print came from (grams per spool), replacing earlier charges."""
    p = inv.get_printer(body["id"])
    total = printer.job_total(p["host"], body["job_id"])  # from the printer's record, not the page
    if not total:
        raise IOError("The printer has no filament total for that print.")
    spools = {s["id"]: s for s in inv.list_all()}
    allocations = []
    for a in body.get("allocations") or []:
        sp = spools.get(int(a["spool_id"]))
        grams = float(a.get("grams") or 0)
        if not sp or grams <= 0:
            continue
        per_mm = inv.mm_to_g(1, inv.type_of(sp["material"], cfs.MATERIALS))
        allocations.append({"spool_id": sp["id"], "mm": grams / per_mm})
    inv.set_job_charges(f"{p['id']}:{body['job_id']}", allocations, total, cfs.MATERIALS)
    return {"ok": True}


def test_printer(host):
    """Check a printer before saving it: CFS reachable? Moonraker (usage tracking) reachable?"""
    if not printer.valid_host(host):
        raise IOError("That doesn't look like an IP address, e.g. 192.168.1.50.")
    data = printer.fetch_slots(host)
    try:
        printer.fetch_job(host)
        moonraker = True
    except IOError:
        moonraker = False
    loaded = sum(1 for s in data["slots"] if s["present"] and s["color"])
    return {"ok": True, "cfs": not data.get("no_cfs"), "slots": len(data["slots"]), "loaded": loaded,
            "moonraker": moonraker}


def get_tag():
    rs = cfs.readers()
    if not rs:
        raise IOError("No NFC reader found. Plug it in and quit NFC Agent / other NFC apps.")
    t = cfs.Tag.__new__(cfs.Tag)
    t.reader, t.conn, t.uid = rs[0], None, None
    return t


# ---------------------------------------------------------------- backups
PICKED = {"restore": None}  # the backup file the user chose, so restore only ever uses that one
BACKUP_CHECK_SECS = 600


def _backup_loop():
    last_err = None
    while True:
        try:
            inv.run_scheduled_backup()
            err = inv.get_pref("backup_error")
            if err and err != last_err:
                on_error(f"backup: {err}")
            last_err = err
        except Exception as e:
            on_error(f"backup: {e}")
        time.sleep(BACKUP_CHECK_SECS)


def start_backup_scheduler():
    threading.Thread(target=_backup_loop, daemon=True).start()


def _downloads(name):
    return os.path.join(os.path.expanduser("~/Downloads"), name)


def backup_api(path, body):
    native = "choose_folder" in NATIVE
    if path == "/api/backup/status":
        return {**inv.backup_settings(), "native": native, "check_secs": BACKUP_CHECK_SECS}
    if path == "/api/backup/settings":
        return inv.set_backup_settings(body)
    if path == "/api/backup/choose_dir":
        folder = NATIVE["choose_folder"]() if native else None
        if folder:
            inv.set_backup_settings({"backup_dir": folder})
        return inv.backup_settings()
    if path == "/api/backup/run_now":  # to the automatic-backup folder, now
        if not inv.get_pref("backup_dir"):
            raise IOError("Choose a backup folder first.")
        out = inv.run_scheduled_backup(force=True)
        if not out:
            raise IOError(inv.get_pref("backup_error") or "The backup didn't run.")
        return {"path": out}
    if path == "/api/backup/save":  # one-off backup to wherever the user picks
        name = inv.backup_name()
        target = NATIVE["save_file"](name) if native else _downloads(name)
        if not target:
            return {"cancelled": True}
        return {"path": inv.backup_to(target)}
    if path == "/api/backup/pick_restore":
        if not native:
            raise IOError("Restoring is available in the app, not in a browser.")
        chosen = NATIVE["open_file"]()
        if not chosen:
            return {"cancelled": True}
        spools = inv.check_backup(chosen)
        PICKED["restore"] = chosen
        return {"path": chosen, "name": os.path.basename(chosen), "spools": spools,
                "modified": os.path.getmtime(chosen)}
    if path == "/api/backup/restore":
        chosen = PICKED["restore"]
        if not chosen or body.get("path") != chosen:
            raise IOError("Choose the backup to restore again.")
        safety = inv.restore_from(chosen)
        PICKED["restore"] = None
        for st in STATE.values():  # slot links may differ in the restored data
            st["swapped"].clear()
        return {"ok": True, "safety": safety}
    if path == "/api/export":
        kind = body.get("kind")
        text = inv.export_csv(kind, cfs.MATERIALS)
        name = f"{APP_NAME}-{'spools' if kind == 'spools' else 'print-usage'}-{time.strftime('%Y-%m-%d')}.csv"
        if not native:
            return {"csv": text, "name": name}  # the page downloads it
        target = NATIVE["save_file"](name)
        if not target:
            return {"cancelled": True}
        with open(target, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads £ correctly
            f.write(text)
        return {"path": target}
    raise IOError("unknown endpoint")


def _quiet(fn, *a):
    try:
        fn(*a)
    except Exception:
        pass


def light_api(path, body):
    """Endpoints that never touch a tag, so they must not wait behind a pending read/write."""
    if path == "/api/support":
        # only ever opens the configured page, never a URL sent by the page
        if SUPPORT_URL:
            webbrowser.open(SUPPORT_URL)
        return {"ok": bool(SUPPORT_URL)}
    if path == "/api/app/show":
        # a second copy of the app being opened asks this one to come forward
        if "show" in NATIVE:
            NATIVE["show"]()
        return {"ok": "show" in NATIVE}
    if path == "/api/open":
        url = LINKS.get(body.get("link"))
        if url:
            webbrowser.open(url)
        return {"ok": bool(url)}
    if path == "/api/update/status":
        if "auto" in body:
            updates.set_auto(bool(body["auto"]))
        return updates.status(APP_VERSION)
    if path == "/api/update/check":
        if body.get("unskip"):  # checking by hand shows a skipped version again
            updates.skip("")
        return check_for_update(force=True)
    if path == "/api/update/skip":
        st = updates.status(APP_VERSION)
        if st["latest"]:
            updates.skip(st["latest"]["version"])
        return updates.status(APP_VERSION)
    if path == "/api/update/open":
        # only ever the release page GitHub gave us (checked in updates.fetch_latest), never a URL from the page
        st = updates.status(APP_VERSION)
        webbrowser.open(st["latest"]["url"] if st["latest"] else updates.RELEASES_PAGE)
        return {"ok": True}
    if path == "/api/status":
        # polled every few seconds by the page; only lists readers, never touches a tag
        try:
            rs = cfs._guard(cfs.readers)
        except cfs.ReaderStuck:
            return {"ok": False, "reader": None, "stuck": True}
        except Exception as e:
            return {"ok": False, "reader": None, "error": str(e)}
        return {"ok": bool(rs), "reader": str(rs[0]) if rs else None}
    if path == "/api/serial":
        return {"serial": inv.new_serial()}
    if path.startswith("/api/backup/") or path == "/api/export":
        return backup_api(path, body)
    if path == "/api/notify/settings":
        for kind, _, _ in NOTIFY_KINDS:
            if kind in body:
                inv.set_pref(f"notify_{kind}", "1" if body[kind] else "0")
        if body.get("humidity_max"):
            inv.set_settings({"humidity_max": body["humidity_max"]})
        return {"available": "notify" in NATIVE, "humidity_max": inv.get_settings()["humidity_max"],
                "kinds": [{"kind": k, "label": l, "help": h, "on": notify_enabled(k)} for k, l, h in NOTIFY_KINDS]}
    if path == "/api/notify/test":
        if "notify" not in NATIVE:
            raise IOError("Notifications are available in the app, not in a browser.")
        NATIVE["notify"](APP_NAME, "Notifications are working.")
        return {"ok": True}
    if path == "/api/app/settings":
        if "settings" not in NATIVE:
            return {"native": False}
        return NATIVE["settings"](body or None)
    if path == "/api/printers/list":
        return {"printers": [printer_summary(p) for p in inv.list_printers()], "models": inv.PRINTER_MODELS}
    if path == "/api/printers/test":
        return test_printer((body.get("host") or "").strip())
    if path == "/api/printers/save":
        if not printer.valid_host((body.get("host") or "").strip()):
            raise IOError("That doesn't look like an IP address, e.g. 192.168.1.50.")
        p = inv.save_printer(body)
        STATE.pop(p["id"], None)  # host may have changed: start fresh
        threading.Thread(target=lambda: _quiet(printer_refresh, p["id"]), daemon=True).start()
        return {"printer": p}
    if path == "/api/printers/delete":
        inv.delete_printer(body["id"])
        STATE.pop(int(body["id"]), None)
        return {"ok": True}
    if path == "/api/printer/status":
        return printer_detail(body["id"], refresh=body.get("refresh", True))
    if path == "/api/printer/link":
        return printer_link(body)
    if path == "/api/printer/assign":
        inv.assign_usage(body["usage_id"], body["spool_id"], cfs.MATERIALS)
        return {"ok": True}
    if path == "/api/printer/assign_job":
        # the amount comes from the printer's own record of the job, not from the page
        p = inv.get_printer(body["id"])
        mm = printer.job_total(p["host"], body["job_id"])
        if not mm:
            raise IOError("The printer has no filament total for that print.")
        return {"grams": inv.add_job_usage(f"{p['id']}:{body['job_id']}", body["spool_id"], mm, cfs.MATERIALS)}
    if path == "/api/printer/history":
        return printer_history(body["id"], int(body.get("limit") or 50), int(body.get("start") or 0))
    if path == "/api/printer/files":
        return {"files": printer.list_files(inv.get_printer(body["id"])["host"])}
    if path == "/api/printer/check_file":
        p = inv.get_printer(body["id"])
        plan = printer.fetch_plan(p["host"], body["file"])
        if not plan:
            raise IOError("That file doesn't say how much filament it needs (it wasn't sliced with Creality Print or OrcaSlicer).")
        live = pstate(p["id"]).get("fit") or {}
        reserved = {}
        for i in live.get("items") or []:  # what the print that's running still needs
            if i.get("slot_key"):
                reserved[i["slot_key"]] = reserved.get(i["slot_key"], 0) + i.get("need_mm", 0)
        return {"file": body["file"], "after_current": bool(reserved),
                "items": fit_items(p, plan, (pstate(p["id"])["data"] or {}).get("slots", []), reserved=reserved)}
    if path == "/api/printer/job_plan":
        return job_plan(int(body["id"]), body.get("file") or "")
    if path == "/api/printer/job_charges":
        return job_charges(body)
    if path == "/api/printer/skip_job":
        inv.set_job_skipped(f"{int(body['id'])}:{body['job_id']}", bool(body.get("skip")))
        return {"ok": True}
    if path == "/api/shopping":
        if body.get("action"):
            inv.shopping_update(body["action"], body.get("key", ""), body.get("qty"))
        groups = inv.filament_groups()
        return {"items": inv.shopping_list(cfs.MATERIALS),
                "filaments": [{"key": k, "material": g["material"], "color": g["color"],
                               "name": cfs.MATERIALS.get(g["material"], g["material"])} for k, g in groups.items()]}
    if path == "/api/shopping/email":
        # only ever opens a new email with the list in it
        text = str(body.get("text") or "")[:20000]
        webbrowser.open("mailto:?" + urllib.parse.urlencode({"subject": "Filament shopping list", "body": text},
                                                           quote_via=urllib.parse.quote))
        return {"ok": True}
    if path == "/api/inv/list":
        return {"spools": inv.list_all(), "in_printer": spools_in_printer()}
    if path == "/api/inv/find":
        return {"spool": inv.find_serial(body.get("serial"))}
    if path == "/api/inv/save":
        # every new spool comes from a scanned (or just-written) tag, so stock stays accurate
        if not body.get("id") and not (body.get("serial") or body.get("uids")):
            raise IOError("Scan the spool's tag to add it to your inventory.")
        return {"spool": inv.save(body)}
    if path == "/api/inv/settings":
        return {"settings": inv.set_settings(body) if body else inv.get_settings()}
    if path == "/api/inv/delete_many":
        ids = [int(i) for i in body.get("ids") or []]
        return {"deleted": inv.delete_many(ids), "ids": ids}
    if path == "/api/inv/trash":
        return {"spools": inv.deleted_spools(), "days": inv.TRASH_DAYS}
    if path == "/api/inv/restore":
        return {"restored": inv.restore(body.get("ids") or [])}
    if path == "/api/inv/purge":
        ids = [s["id"] for s in inv.deleted_spools()] if body.get("all") else (body.get("ids") or [])
        return {"purged": inv.purge_deleted(ids)}
    if path == "/api/inv/delete":
        inv.delete(body["id"])
        return {"ok": True}


def api(path, body):
    tag = get_tag()
    try:
        return tag_op(tag, path, body)
    finally:
        tag.close()  # never leave a connection open between operations


def tag_op(tag, path, body):
    CANCEL.clear()
    uid = tag.wait(None, timeout=30, exclude_uid=body.get("exclude_uid"), cancel=CANCEL)
    if uid is None:
        raise IOError("Cancelled." if CANCEL.is_set() else "No tag detected within 30 seconds.")

    if path == "/api/read":
        return {"uid": uid.hex().upper(), "data": cfs.do_read(tag)}
    if path == "/api/inv/scan":
        data = cfs.do_read(tag)
        return {"uid": uid.hex().upper(), "data": data, "spool": inv.find_serial(data["serial"]),
                "deleted_spool": inv.find_serial(data["serial"], deleted=True)}
    if path == "/api/format":
        cfs.do_format(tag)
        return {"uid": uid.hex().upper()}
    if path == "/api/write":
        color = body["color"].lstrip("#").upper()
        rec = cfs.build_record(body["material"], color, cfs.WEIGHTS[body["weight"]],
                               body["serial"], body["printer"])
        cfs.do_write(tag, rec)
        return {"uid": uid.hex().upper()}
    raise IOError("unknown endpoint")


# ---------------------------------------------------------------- the page (web/)
def web_dir():
    """The web/ folder: next to this file, or inside the .app when built with PyInstaller."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "web")


def web_file(url_path):
    """The file for a URL path inside web/, or None (never anything outside it)."""
    root = os.path.realpath(web_dir())
    full = os.path.realpath(os.path.join(root, url_path.lstrip("/")))
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        return None
    return full


def page():
    with open(os.path.join(web_dir(), "index.html"), encoding="utf-8") as f:
        html = f.read()
    config = {"materials": cfs.MATERIALS, "weights": list(cfs.WEIGHTS), "grams": inv.GRAMS,
              "support": bool(SUPPORT_URL), "platform": PLATFORM}
    return (html.replace("__CONFIG__", json.dumps(config)).replace("__VERSION__", APP_VERSION)
            .replace("__APP_NAME__", APP_NAME))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, payload, ctype="application/json", cache=True):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if not cache:  # the files carry ?v=<version>, but never let an old copy linger after an update
            self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, page().encode(), "text/html; charset=utf-8", cache=False)
        file = web_file(path)
        if file:
            with open(file, "rb") as f:
                ctype = mimetypes.guess_type(file)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                return self._send(200, f.read(), ctype, cache=False)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        # only accept requests from our own page
        if self.headers.get("X-CFS") != "1":
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) or b"{}"
        if self.path == "/api/cancel":  # must not wait on LOCK: the request to cancel holds it
            CANCEL.set()
            return self._send(200, {"ok": True})
        try:
            body = json.loads(raw)
            quick = light_api(self.path, body)
            if quick is not None:
                return self._send(200, quick)
            if not LOCK.acquire(timeout=LOCK_TIMEOUT):
                raise IOError("The reader is busy with another operation. If this keeps happening, "
                              "unplug the reader and plug it back in.")
            try:
                self._send(200, api(self.path, body))
            finally:
                LOCK.release()
        except Exception as e:
            if str(e) not in ("Cancelled.", "No tag detected within 30 seconds."):
                on_error(f"{self.path}: " + traceback.format_exc())
            self._send(200, {"error": str(e)})


if __name__ == "__main__":
    srv = LocalServer(("127.0.0.1", PORT), Handler)
    start_printer_sync()
    start_backup_scheduler()
    start_watchers()
    url = f"http://127.0.0.1:{PORT}"
    print(f"{APP_NAME} running at {url}  (Ctrl+C to quit)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBye")

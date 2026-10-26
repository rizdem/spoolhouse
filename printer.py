"""
printer.py - read a Creality K-series printer's CFS slots over the local network.

Uses the printer's own WebSocket (port 9999, the one Creality Print talks to) and only sends
the read-only `get boxsInfo` request, so it is safe while the printer is printing.

Each slot reports its material code (e.g. 01001 = Hyper PLA), colour and `remaining_length` in mm,
which the CFS counts down from the length written on the spool's tag (330 m for 1 kg).
"""
import json
import re
import time
import urllib.parse
import urllib.request

import websocket

PORT = 9999
MOONRAKER_PORT = 7125
TIMEOUT = 4.0  # seconds to connect and to wait for the answer

_HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def valid_host(host):
    return bool(host) and bool(_HOST_RE.match(host))


def _hex6(color):
    # printer streams "#0RRGGBB" (a pad digit first) or "#RRGGBB"; multi-colour spools are "a,b"
    c = (color or "").split(",")[0].lstrip("#")
    return c[-6:].upper() if len(c) >= 6 else ""


def fetch_slots(host):
    """Return {"boxes": [...], "slots": [...]} for the printer at `host`. Raises IOError."""
    if not valid_host(host):
        raise IOError("Enter the printer's IP address, e.g. 192.168.1.50.")
    try:
        ws = websocket.create_connection(f"ws://{host}:{PORT}", timeout=TIMEOUT)
    except Exception as e:
        raise IOError(f"Can't reach the printer at {host}. Check it's on and the IP is right. ({e})")
    try:
        ws.send(json.dumps({"method": "get", "params": {"boxsInfo": 1}}))
        end = time.time() + TIMEOUT
        info = None
        while time.time() < end and info is None:
            try:
                msg = json.loads(ws.recv())
            except (ValueError, TypeError):
                continue  # heartbeat "ok" and other non-JSON frames
            except websocket.WebSocketTimeoutException:
                break
            if isinstance(msg, dict) and isinstance(msg.get("boxsInfo"), dict):
                info = msg["boxsInfo"]
    finally:
        try:
            ws.close()
        except Exception:
            pass
    if info is None or not info.get("materialBoxs"):
        # no CFS (e.g. a K1 without one): a single spool holder the user can link a spool to
        return {"no_cfs": True,
                "boxes": [{"id": 0, "label": "Spool holder", "external": True, "connected": True,
                           "temp": None, "humidity": None}],
                "slots": [{"key": "0-0", "label": "Spool holder", "present": True, "printing": False,
                           "material_code": "", "vendor": "", "type": "", "name": "Spool holder",
                           "color": "", "remaining_mm": None, "percent": None}]}
    return _normalise(info)


def _normalise(info):
    boxes, slots = [], []
    for b in info.get("materialBoxs") or []:
        external = b.get("type") == 1
        box_id = int(b.get("id", 0))
        box_label = "External" if external else f"CFS {box_id}"
        boxes.append({"id": box_id, "label": box_label, "external": external,
                      "connected": b.get("state") == 1 or external,
                      "temp": b.get("temp"), "humidity": b.get("humidity")})
        for m in b.get("materials") or []:
            sid = int(m.get("id", 0))
            present = bool(m.get("type")) and m.get("state", 0) != 0
            rem = m.get("remaining_length")
            slots.append({
                "key": f"{box_id}-{sid}",
                "label": box_label if external else f"{box_label} · Slot {sid + 1}",
                "present": present,
                "printing": bool(m.get("selected")),
                "material_code": str(m.get("rfid") or ""),
                "vendor": m.get("vendor") or "",
                "type": m.get("type") or "",
                "name": m.get("name") or "",
                "color": _hex6(m.get("color")),
                "remaining_mm": float(rem) if present and rem is not None else None,
                "percent": m.get("percent"),
            })
    return {"boxes": boxes, "slots": slots}


def fetch_history(host, limit=50, start=0):
    """Print jobs from Moonraker's job history, newest first (read-only HTTP GET)."""
    if not valid_host(host):
        raise IOError("Enter the printer's IP address first.")
    q = urllib.parse.urlencode({"limit": int(limit), "start": int(start), "order": "desc"})
    try:
        with urllib.request.urlopen(f"http://{host}:{MOONRAKER_PORT}/server/history/list?{q}",
                                    timeout=TIMEOUT + 2) as r:
            data = json.load(r)["result"]
    except Exception as e:
        raise IOError(f"Couldn't read the print history from {host}. ({e})")
    jobs = []
    for j in data.get("jobs") or []:
        name = j.get("filename") or ""
        # Creality Print names files like "Part_PETG_1h26m.gcode": use the type as a fallback
        m = re.search(r"_(PLA-CF|PLA|PETG-CF|PETG|ABS|ASA|TPU|PA-CF|PA|PC|PET)_", name, re.I)
        jobs.append({
            "id": j.get("job_id"),
            "file": name,
            "name": re.sub(r"\.gcode$", "", name, flags=re.I),
            "status": j.get("status") or "",
            "start": j.get("start_time"),
            "end": j.get("end_time"),
            "duration": j.get("print_duration") or 0,
            "mm": j.get("filament_used") or 0,
            "type_hint": m.group(1).upper() if m else "",
        })
    # Moonraker only fills a job's totals when it ends: read the running one live
    for job in jobs:
        if job["status"] == "in_progress":
            try:
                with urllib.request.urlopen(f"http://{host}:{MOONRAKER_PORT}/printer/objects/query?print_stats",
                                            timeout=TIMEOUT) as r:
                    ps = json.load(r)["result"]["status"]["print_stats"]
                job["mm"], job["duration"] = ps.get("filament_used") or 0, ps.get("print_duration") or 0
            except Exception:
                pass
    return {"jobs": jobs, "total": data.get("count", len(jobs))}


def fetch_job(host):
    """The current/last job from Moonraker: state, filament used so far (mm) and its job id."""
    def get(path):
        with urllib.request.urlopen(f"http://{host}:{MOONRAKER_PORT}{path}", timeout=TIMEOUT) as r:
            return json.load(r)["result"]
    try:
        ps = get("/printer/objects/query?print_stats")["status"]["print_stats"]
        last = (get("/server/history/list?limit=1&order=desc").get("jobs") or [None])[0]
    except Exception as e:
        raise IOError(f"Couldn't read the current print from {host}. ({e})")
    name = ps.get("filename") or (last or {}).get("filename") or ""
    m = re.search(r"_(PLA-CF|PLA|PETG-CF|PETG|ABS|ASA|TPU|PA-CF|PA|PC|PET)_", name, re.I)
    return {
        "filename": name,
        "state": ps.get("state") or "",            # printing, paused, complete, cancelled, standby, error
        "used_mm": float(ps.get("filament_used") or 0),
        "job_id": (last or {}).get("job_id"),
        "job_status": (last or {}).get("status"),  # in_progress while the job runs
        "type_hint": m.group(1).upper() if m else "",
    }


def job_total(host, job_id):
    """Final filament used by a finished job, from the history (None if not found)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{MOONRAKER_PORT}/server/history/job?uid={urllib.parse.quote(str(job_id))}",
                                    timeout=TIMEOUT) as r:
            return float(json.load(r)["result"]["job"].get("filament_used") or 0)
    except Exception:
        return None


# ---------------------------------------------------------------- print plans (from the G-code file)
_PLAN_CACHE = {}  # filename -> plan; print files don't change once uploaded
_PLAN_KEYS = {
    "filament used [mm]": "mm", "filament used [g]": "g",
    "filament_colour": "color", "filament_type": "type", "filament_vendor": "vendor", "filament_ids": "id",
}


def _split(v):
    v = v.strip().strip('"')
    parts = v.split(";") if ";" in v else v.split(",")
    return [x.strip().strip('"') for x in parts]


def parse_plan(text):
    """Per-filament usage from the comment block slicers write at the end of a G-code file:
    '; filament used [g] = 59.81, 1.01, 0.00' and '; filament_colour = #FFFFFF;#FF0000;...'."""
    found = {}
    for line in text.splitlines():
        if not line.startswith("; ") or " = " not in line:
            continue
        key, _, val = line[2:].partition(" = ")
        if key in _PLAN_KEYS and _PLAN_KEYS[key] not in found:
            found[_PLAN_KEYS[key]] = _split(val)
    if "mm" not in found:
        return None
    out = []
    for i, mm in enumerate(found["mm"]):
        try:
            mm = float(mm)
        except ValueError:
            continue
        if mm <= 0:
            continue
        get = lambda k: (found.get(k) or [])[i] if i < len(found.get(k) or []) else ""
        try:
            g = float(get("g") or 0)
        except ValueError:
            g = 0.0
        out.append({"index": i, "mm": mm, "g": g, "color": get("color").lstrip("#").upper()[:6],
                    "type": get("type").upper(), "vendor": get("vendor"), "id": get("id")})
    return out


def fetch_plan(host, filename):
    """The filament plan for a print file on the printer (cached). None if the file has none."""
    if not filename:
        return None
    if filename in _PLAN_CACHE:
        return _PLAN_CACHE[filename]
    url = f"http://{host}:{MOONRAKER_PORT}/server/files/gcodes/{urllib.parse.quote(filename)}"
    req = urllib.request.Request(url, headers={"Range": "bytes=-300000"})  # the summary is at the end
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT + 6) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    plan = parse_plan(text)
    _PLAN_CACHE[filename] = plan
    return plan


def list_files(host, limit=30):
    """Print files on the printer, newest first."""
    try:
        with urllib.request.urlopen(f"http://{host}:{MOONRAKER_PORT}/server/files/list?root=gcodes",
                                    timeout=TIMEOUT + 2) as r:
            files = json.load(r)["result"]
    except Exception as e:
        raise IOError(f"Couldn't list the print files on {host}. ({e})")
    files = [f for f in files if f.get("path", "").lower().endswith(".gcode")]
    files.sort(key=lambda f: f.get("modified") or 0, reverse=True)
    return [{"name": f["path"], "modified": f.get("modified"), "size": f.get("size")} for f in files[:limit]]


def color_distance(a, b):
    try:
        ra, ga, ba = (int(a[i:i + 2], 16) for i in (0, 2, 4))
        rb, gb, bb = (int(b[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return 999
    return ((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2) ** 0.5


# ---------------------------------------------------------------- tags loaded in the CFS
def parse_tag_record(rec):
    """A CFS tag record as Klipper reports it (the decrypted text the CFS read from the spool's tag):
    date(5) vendor(4) batch(2) '1'+material(5) '0'+colour(6) length(4) serial(6) ..."""
    rec = (rec or "").strip()
    if len(rec) < 34 or rec.lower() == "none":
        return None
    material, color, serial = rec[12:17], rec[18:24].upper(), rec[28:34]
    if not (material.isdigit() and serial.isalnum()):
        return None
    return {"material": material, "color": color, "length": rec[24:28], "serial": serial, "vendor": rec[5:9]}


def fetch_box(host):
    """Klipper's 'box' object (the CFS) over Moonraker, read-only; {} if the printer doesn't report it."""
    try:
        with urllib.request.urlopen(f"http://{host}:{MOONRAKER_PORT}/printer/objects/query?box",
                                    timeout=TIMEOUT) as r:
            return json.load(r)["result"]["status"].get("box") or {}
    except Exception:
        return {}


def slot_routing(box):
    """How the printer feeds a print's filaments: {filament index: '<box>-<slot>'}. A print's filament 0 is
    logical slot T1A, 1 is T1B ... 4 is T2A; the box's 'map' says which physical slot actually feeds it."""
    out = {}
    for logical, physical in (box.get("map") or {}).items():
        m, n = re.fullmatch(r"T(\d)([A-D])", logical), re.fullmatch(r"T(\d)([A-D])", physical or "")
        if m and n:
            index = (int(m.group(1)) - 1) * 4 + "ABCD".index(m.group(2))
            out[index] = f"{int(n.group(1))}-{'ABCD'.index(n.group(2))}"
    return out


def fetch_box_tags(host, box=None):
    """{'<box>-<slot>': tag} for each CFS slot whose spool tag the printer has read (Klipper's 'box'
    object over Moonraker, read-only). Empty if the printer doesn't report it."""
    box = fetch_box(host) if box is None else box
    out = {}
    for name, unit in box.items():
        m = re.fullmatch(r"T(\d+)", name)
        if not m or not isinstance(unit, dict):
            continue
        for i, rec in enumerate(unit.get("vender") or []):
            tag = parse_tag_record(rec if isinstance(rec, str) else "")
            if tag:
                out[f"{int(m.group(1))}-{i}"] = tag
    return out

"""Reading printer data: CFS slots, print-file plans and colours. No network involved."""
import pytest

import printer

# the summary Creality Print writes at the end of a G-code file (from a real two-colour print)
PLAN_TEXT = """\
; filament used [mm] = 19892.67, 334.76, 0.00
; filament used [cm3] = 47.85, 0.81, 0.00
; filament used [g] = 59.81, 1.01, 0.00
; total filament used [g] = 60.82
; CONFIG_BLOCK_START
; filament_colour = #FFFFFF;#FF0000;#E3CB1C
; filament_ids = 00001;00001;00001
; filament_type = PLA;PLA;PLA
; filament_vendor = Generic;Generic;Generic
"""

# boxsInfo as a K2 Pro sent it over its WebSocket (trimmed)
BOXS_INFO = {"materialBoxs": [
    {"id": 0, "state": 0, "type": 1, "materials": [
        {"id": 0, "vendor": "", "type": "", "color": "", "name": "", "percent": 100, "state": 1}]},
    {"id": 1, "state": 1, "type": 0, "temp": 31.0, "humidity": 36.0, "materials": [
        {"id": 0, "vendor": "Creality", "type": "PLA", "name": "Hyper PLA", "rfid": "01001", "color": "#0ffffff",
         "percent": 53, "state": 2, "selected": 1, "remaining_length": 87450.0},
        {"id": 1, "vendor": "Creality", "type": "PLA", "name": "EN-PLA+", "rfid": "09001", "color": "#0ff0000",
         "percent": 100, "state": 2, "selected": 0, "remaining_length": 330000.0},
        {"id": 2, "vendor": "", "type": "", "name": "", "rfid": "", "color": "", "percent": 100, "state": 0}]}]}


def test_plan_parsing():
    plan = printer.parse_plan(PLAN_TEXT)
    assert [(f["index"], f["color"], f["type"], f["g"]) for f in plan] == [(0, "FFFFFF", "PLA", 59.81), (1, "FF0000", "PLA", 1.01)]
    assert plan[0]["mm"] == pytest.approx(19892.67) and plan[0]["id"] == "00001"


def test_plan_missing():
    assert printer.parse_plan("; nothing useful here\nG1 X0") is None


def test_cfs_slots_are_normalised():
    d = printer._normalise(BOXS_INFO)
    slots = {s["key"]: s for s in d["slots"]}
    assert slots["1-0"]["color"] == "FFFFFF" and slots["1-0"]["printing"] and slots["1-0"]["remaining_mm"] == 87450
    assert slots["1-1"]["material_code"] == "09001" and slots["1-1"]["label"] == "CFS 1 · Slot 2"
    assert not slots["1-2"]["present"] and slots["1-2"]["remaining_mm"] is None
    assert not slots["0-0"]["present"]  # empty external holder
    box = next(b for b in d["boxes"] if b["id"] == 1)
    assert box["humidity"] == 36 and box["connected"]


def test_colour_distance():
    assert printer.color_distance("FFFFFF", "FFFFFF") == 0
    assert printer.color_distance("4C8D2B", "00A651") < 160  # slicer green vs a real green spool
    assert printer.color_distance("FFFFFF", "000000") > 400
    assert printer.color_distance("nope", "FFFFFF") == 999


def test_host_validation():
    assert printer.valid_host("192.168.1.50") and printer.valid_host("k2.local")
    assert not printer.valid_host("bad host!") and not printer.valid_host("")
    with pytest.raises(IOError):
        printer.fetch_slots("bad host!")


def test_printer_routing_of_filaments_to_slots():
    # as a K2 Pro reported it while printing a file whose filament 0 was fed from slot C
    box = {"map": {"T1A": "T1C", "T1B": "T1B", "T1C": "T1C", "T2A": "T2A"}}
    assert printer.slot_routing(box) == {0: "1-2", 1: "1-1", 2: "1-2", 4: "2-0"}
    assert printer.slot_routing({}) == {}


def test_job_progress_and_time_left(monkeypatch):
    import io
    import json as _json
    replies = {
        "/printer/objects/query": {"status": {"print_stats": {"state": "printing", "filename": "box.gcode",
                                                              "filament_used": 1234.5, "print_duration": 3600},
                                              "virtual_sdcard": {"progress": 0.4}}},
        "/server/history/list": {"jobs": [{"job_id": "0000AA", "status": "in_progress", "filename": "box.gcode"}]},
        "/server/files/metadata": {"estimated_time": None},
    }

    def fake(url, timeout=None):
        path = url.split(":7125", 1)[1].split("?", 1)[0]
        return io.BytesIO(_json.dumps({"result": replies[path]}).encode())
    monkeypatch.setattr(printer.urllib.request, "urlopen", fake)
    printer._ESTIMATES.clear()
    job = printer.fetch_job("k2.local")
    assert job["progress"] == 0.4 and job["print_secs"] == 3600
    assert job["left_secs"] == 5400            # 40% in an hour: about 1.5 h to go
    replies["/server/files/metadata"] = {"estimated_time": 10000}
    printer._ESTIMATES.clear()
    assert printer.fetch_job("k2.local")["left_secs"] == 6400   # the slicer's estimate wins
    replies["/printer/objects/query"]["status"]["print_stats"]["state"] = "standby"
    assert printer.fetch_job("k2.local")["progress"] is None


def test_time_left_from_the_printers_screen():
    import cfs_gui
    job = {"state": "printing", "left_secs": 780, "progress": 0.3}
    cfs_gui.screen_time(job, {"printLeftTime": 1080, "printProgress": 12})
    assert job["left_secs"] == 1080 and job["progress"] == 0.12
    idle = {"state": "complete", "left_secs": None, "progress": None}
    cfs_gui.screen_time(idle, {"printLeftTime": 0, "printProgress": 100})
    assert idle["left_secs"] is None
    kept = {"state": "printing", "left_secs": 780, "progress": 0.3}
    cfs_gui.screen_time(kept, {})  # the printer didn't say: keep the estimate
    assert kept["left_secs"] == 780

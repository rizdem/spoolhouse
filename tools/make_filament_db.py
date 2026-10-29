"""Make web/filaments.json: brands' filaments (colours, temperatures, empty spool weight) for picking a brand
when writing tags, from SpoolmanDB (github.com/Donkie/SpoolmanDB, MIT licence), trimmed to 1.75 mm filament
and the fields Spoolhouse uses. The same file goes into the Android app (copy it to its assets).

    python3 tools/make_filament_db.py            # downloads the latest SpoolmanDB
    python3 tools/make_filament_db.py file.json  # or uses a copy you have
"""
import datetime
import json
import os
import sys
import urllib.request

URL = "https://donkie.github.io/SpoolmanDB/filaments.json"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "filaments.json")


def rng(r):
    return [int(r[0]), int(r[1])] if isinstance(r, list) and len(r) == 2 else None


def main():
    if len(sys.argv) > 1:
        raw = json.load(open(sys.argv[1]))
    else:
        with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Spoolhouse"}), timeout=30) as r:
            raw = json.load(r)
    brands = {}
    for f in raw:
        if abs(float(f.get("diameter") or 0) - 1.75) > 0.01:
            continue  # the CFS takes 1.75 mm
        hexes = f.get("color_hexes") or [f.get("color_hex")]
        hexes = [h.lstrip("#").upper()[:6] for h in hexes if h]
        if not hexes:
            continue
        brands.setdefault(f["manufacturer"].strip(), []).append({
            "m": f.get("material", "").strip(),        # material, e.g. PLA
            "n": f.get("name", "").strip(),            # the brand's colour name
            "c": hexes[0],                             # colour (first, for multi-colour)
            "cs": hexes[1:] or None,                   # the other colours of a multi-colour filament
            "w": f.get("weight"),                      # net filament weight, g
            "sw": f.get("spool_weight"),               # empty spool, g
            "t": f.get("extruder_temp"), "tr": rng(f.get("extruder_temp_range")),
            "b": f.get("bed_temp"), "br": rng(f.get("bed_temp_range")),
            "d": f.get("density"),
            "fin": f.get("finish"),                    # matte, glossy...
        })
    out = {
        "source": "SpoolmanDB (github.com/Donkie/SpoolmanDB), MIT licence",
        "fetched": datetime.date.today().isoformat(),
        "brands": [{"name": b, "filaments": [{k: v for k, v in x.items() if v not in (None, "", [])} for x in fs]}
                   for b, fs in sorted(brands.items(), key=lambda kv: kv[0].lower())],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    n = sum(len(b["filaments"]) for b in out["brands"])
    print(f"{OUT}: {len(out['brands'])} brands, {n} filaments, {os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()

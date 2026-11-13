"""Build artnet_map.csv (the config for artnet_govee.py) from devices.json + strips.json.
One row per known device, packed into universes starting at universe 0 / channel 1, never splitting a device across universes.
Channelsets (3 channels = RGB each): H7076 = 3 (seg 0, seg 1, segs 2-35), H60C1 = 3 (one per segment), strips = 8 (even split of x).
Refuses to overwrite an existing CSV (you will have edited it) unless --force.
Usage: python3 -I make_artnet_csv.py [--force]
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "artnet_map.csv")
STRIP_ZONES = 8
FIELDS = ["mac", "govee_id", "sku", "n", "x", "universe", "num_channels", "start_channel", "zones"]
SKU_ORDER = {"H61B6": 0, "H61F2": 1, "H60C1": 2, "H7076": 3}

if os.path.exists(OUT) and "--force" not in sys.argv:
    sys.exit(f"{OUT} exists; pass --force to overwrite it")

devices = json.load(open(os.path.join(HERE, "devices.json")))
strips = {s["device_id"]: s for s in json.load(open(os.path.join(HERE, "strips.json"))).values()}

rows = []
for did, d in devices.items():
    sku = d["sku"]
    if did in strips:
        n, x, zones, count = strips[did]["n"], strips[did]["x"], "", STRIP_ZONES
    elif sku == "H7076":
        n, x, zones, count = 36, 36, "0;1;2-35", 3
    elif sku == "H60C1":
        n, x, zones, count = 3, 3, "0;1;2", 3
    else:
        print(f"skipping {did} ({sku}): no layout known")
        continue
    rows.append({"mac": d["mac"], "govee_id": did, "sku": sku, "n": n, "x": x, "num_channels": 3 * count, "zones": zones})

rows.sort(key=lambda r: (SKU_ORDER[r["sku"]], r["govee_id"]))
universe, cursor = 0, 1
for r in rows:
    if cursor + r["num_channels"] - 1 > 512:
        universe, cursor = universe + 1, 1
    r["universe"], r["start_channel"] = universe, cursor
    cursor += r["num_channels"]

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
print(f"wrote {OUT}: {len(rows)} devices, {sum(r['num_channels'] for r in rows)} channels, universes 0..{universe}")

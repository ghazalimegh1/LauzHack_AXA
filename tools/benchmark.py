"""Accuracy vs cost on your own labelled photos: the chart for the pitch.
Put photos in eval/ and describe them in eval/labels.csv (see eval/labels_example.csv):
    image,water,hail,light_well,door_low,ramp_down,slope_to_house,glass_roof,blinds,car_outside
    house1.jpg,2,1,y,n,n,y,n,y,n
Then:  python tools/benchmark.py
Compares three designs: always-cheap, always-strong, and our cascade."""
import csv
import os
import sys
from pathlib import Path

os.environ["FRUGAL_NO_CACHE"] = "1"  # every design pays for its own calls

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from frugal import checklist, config, hazards, photo, pipeline, vision  # noqa: E402

labels = ROOT / "eval" / "labels.csv"
if not labels.exists():
    sys.exit("Create eval/labels.csv first (copy eval/labels_example.csv).")

totals = {d: {"right": 0, "asked": 0, "usd": 0.0} for d in ("cheap", "strong", "cascade")}
for row in csv.DictReader(labels.open(encoding="utf-8")):
    data = (ROOT / "eval" / row["image"]).read_bytes()
    levels = {"water": int(row["water"]), "hail": int(row["hail"])}
    qs = checklist.select(hazards.from_levels(levels))
    if not qs:
        continue
    img = photo.load(data)
    runs = {
        "cheap": vision.ask(config.CHEAP_MODEL, photo.jpeg(img, config.CHEAP_IMG_PX), qs),
        "strong": vision.ask(config.STRONG_MODEL, photo.jpeg(img, config.NAIVE_IMG_PX, 85), qs),
    }
    casc = pipeline.run(row["image"], data, levels=levels, force=True)
    runs["cascade"] = {"answers": casc["answers"], "usd": casc["ledger"].totals()["usd"]}
    for d, r in runs.items():
        for q in qs:
            totals[d]["asked"] += 1
            totals[d]["right"] += r["answers"].get(q["id"]) == row[q["id"]].strip().lower()
        totals[d]["usd"] += r["usd"] or 0.0

print(f"{'design':<9} {'accuracy':>9} {'USD total':>11}")
for d, t in totals.items():
    acc = t["right"] / t["asked"] if t["asked"] else 0
    print(f"{d:<9} {acc:9.1%} {t['usd']:11.5f}")
if config.MOCK:
    print("\nMOCK mode: numbers are fake. Add OPENROUTER_API_KEY to .env.")

"""Run this once at the start of the hackathon:
    python tools/check_layers.py "Gerberngasse 10, Bern"
It prints what each hazard layer returns at that address (via the federal WMS point
query, the same call the app makes), so you can see which layers answer and with which
attribute names."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frugal import geo, hazards  # noqa: E402

address = sys.argv[1] if len(sys.argv) > 1 else "Gerberngasse 10, Bern"
place = geo.geocode(address)
print("Place:", place)
for layer in hazards.LAYERS:
    res = hazards.parse_wms(hazards._wms_text(place["e"], place["n"], [layer["id"]]))
    print(f"\n== {layer['id']}  ({len(res)} result(s))")
    for r in res[:3]:
        print(json.dumps(r["attributes"], ensure_ascii=False)[:500])
summary = hazards.from_map(place["e"], place["n"])
print("\nLevels:", {g: hazards.LEVEL_NAMES[v["level"]] for g, v in summary.items()})
print("Summary:", json.dumps(summary, indent=1)[:1500])
print("\nTip: the flood layers only cover mapped zones, so 0 results is normal outside them. "
      "Try an address you know is in a flood zone (e.g. the Matte in Bern) to see a hit.")

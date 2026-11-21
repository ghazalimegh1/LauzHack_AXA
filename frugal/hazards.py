"""Turns raw map answers into one simple level per hazard group:
0 = low, 1 = medium, 2 = high. Two groups: 'water' (rivers + surface runoff) and 'hail',
the two biggest insured natural-hazard costs in Switzerland.

How the maps are asked (checked live on 2026-11-21):
the REST 'identify' endpoint answers "No GeoTable was found" for all four layers below,
because they are raster/WMS layers. The federal WMS answers a point query
(GetFeatureInfo) for all of them, so we use that. Still free, still one request.
"""
from __future__ import annotations

import re

import requests

from . import cache, config, geo

GROUPS = ("water", "hail")
LEVEL_NAMES = {0: "low", 1: "medium", 2: "high"}
WMS = "https://wms.geo.admin.ch/"

# Being inside a mapped zone is the signal. The flood layers return a feature id but
# no attributes, so presence is all we can read. The hail layer returns one value.
LAYERS = [
    {"id": "ch.bafu.aquaprotect_100", "group": "water", "if_present": 2,
     "label": "River/lake flood area, 100-year (Aquaprotect, coarse)"},
    {"id": "ch.bafu.aquaprotect_500", "group": "water", "if_present": 1,
     "label": "River/lake flood area, 500-year (Aquaprotect, coarse)"},
    {"id": "ch.bafu.gefaehrdungskarte-oberflaechenabfluss", "group": "water", "if_present": 1,
     "label": "Surface runoff hazard map"},
    # Value is the hail size in cm (MeteoSwiss legend: <1.5, 1.5-2.5, 2.5-3.5, 3.5-4.5, >=4.5 cm).
    # Seen live: Lausanne 3.5, Bern 4. The 3/4 cm cut-offs are our team's assumption.
    {"id": "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre", "group": "hail",
     "numeric_cm": (3.0, 4.0),  # 50-year hail size: >=3 cm medium, >=4 cm high
     "label": "Hail size, 50-year return period (MeteoSwiss)"},
]

_VALUE_KEYS = ("value_0", "value", "val", "wert", "korngroesse", "grain_size", "hail_size", "size")
_SKIP_KEYS = {"id", "gid", "fid", "objectid", "label", "name", "bfs", "featureid", "feature"}


# ---------------- asking the map ----------------
def _wms_text(e: float, n: float, layer_ids: list[str]) -> str:
    """One GetFeatureInfo request for all layers, as plain text (the JSON variant returns
    whole flood polygons, which can be megabytes; the text variant is a few lines)."""
    ids = ",".join(layer_ids)
    params = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo",
        "LAYERS": ids, "QUERY_LAYERS": ids, "STYLES": "", "CRS": "EPSG:2056",
        # 100 m box at 101 px: one pixel is about 1 m, the point is the centre pixel.
        "BBOX": f"{e - 50:.1f},{n - 50:.1f},{e + 50:.1f},{n + 50:.1f}",
        "WIDTH": 101, "HEIGHT": 101, "I": 50, "J": 50,
        "INFO_FORMAT": "text/plain", "FEATURE_COUNT": 5,
    }
    k = cache.key(WMS, repr(sorted(params.items())))
    hit = cache.get("geo", k)
    if hit is not None:
        return hit
    try:
        r = requests.get(WMS, params=params, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise geo.GeoError(str(exc)) from exc
    cache.put("geo", k, r.text)
    return r.text


def parse_wms(text: str) -> list[dict]:
    """Reads MapServer's text answer:
        Layer 'ch.x'
          Feature 0:
            ch.x.value_0.name = '4'
    into [{"layerBodId": "ch.x", "attributes": {"feature": "0", "value_0": "4"}}]."""
    out, layer = [], None
    for line in (text or "").splitlines():
        line = line.strip()
        if m := re.match(r"Layer '([^']+)'", line):
            layer = m.group(1)
        elif (m := re.match(r"Feature (\S+?):", line)) and layer:
            out.append({"layerBodId": layer, "attributes": {"feature": m.group(1)}})
        elif (m := re.match(r"(\S+) = '(.*)'$", line)) and out:
            out[-1]["attributes"][_short_key(m.group(1), layer)] = m.group(2)
    return out


def _short_key(key: str, layer: str | None) -> str:
    # 'ch.x.value_0.name' -> 'value_0': drop the layer prefix and MapServer's '.name' suffix.
    if layer and key.startswith(layer + "."):
        key = key[len(layer) + 1:]
    return key[:-5] if key.endswith(".name") else key


# ---------------- turning answers into levels ----------------
def _number(attrs: dict) -> float | None:
    # Prefer fields that look like a value; otherwise take the first numeric field.
    ordered = [k for k in attrs if k.lower() in _VALUE_KEYS] + list(attrs)
    for k in ordered:
        if k.lower() in _SKIP_KEYS:
            continue
        try:
            return float(attrs[k])
        except (TypeError, ValueError):
            continue
    return None


def _level_for(layer: dict, attrs: dict) -> int:
    if "if_present" in layer:
        return layer["if_present"]
    v = _number(attrs)
    if v is None:
        return 1  # inside the layer but value unreadable: be cautious, not alarmist
    if v > 15:
        v /= 10  # value is probably in mm, thresholds are in cm
    lo, hi = layer["numeric_cm"]
    return 2 if v >= hi else 1 if v >= lo else 0


def empty() -> dict:
    return {g: {"level": 0, "sources": [], "raw": [], "answered": False} for g in GROUPS}


def from_map(e: float, n: float) -> dict:
    out = empty()
    results = parse_wms(_wms_text(e, n, [l["id"] for l in LAYERS]))
    by_id = {l["id"]: l for l in LAYERS}
    for res in results:
        layer = by_id.get(res.get("layerBodId"))
        if not layer:
            continue
        attrs = res["attributes"]
        g = out[layer["group"]]
        g["answered"] = True
        g["level"] = max(g["level"], _level_for(layer, attrs))
        if layer["label"] not in g["sources"]:
            g["sources"].append(layer["label"])
        g["raw"].append({"layer": layer["id"], "attributes": attrs})
    return out


def from_levels(levels: dict) -> dict:
    """Used by the developer override and the benchmark: skip the map entirely."""
    out = empty()
    for g, lvl in levels.items():
        out[g].update(level=int(lvl), sources=["manual / test value"], answered=True)
    return out

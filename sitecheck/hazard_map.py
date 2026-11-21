"""Address -> Swiss map coordinates -> what the official hazard maps say at that point.

Free federal services, no AI:
- geocoding: geo.admin.ch SearchServer
- hazard maps: geo.admin.ch WMS, one GetFeatureInfo point query for all layers

Result per hazard: level 0, 1 or 2, or "available": False when the map did not answer.
A missing answer is never turned into "low".
"""
from __future__ import annotations

import re

import requests

from . import cache, settings

SEARCH = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
WMS = "https://wms.geo.admin.ch/"

HAIL_LAYER = "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre"
# Hail size in cm with a 50-year return period. Our team's cut-offs: >= 3 cm is level 1,
# >= 4 cm is level 2.
HAIL_CUTOFFS_CM = (3.0, 4.0)
# Flood layers: being inside a mapped zone is the signal (they carry no readable value).
WATER_LAYERS = {
    "ch.bafu.gefaehrdungskarte-oberflaechenabfluss": (1, "Surface runoff hazard map (FOEN)"),
    "ch.bafu.aquaprotect_500": (1, "Flood area, 500-year (Aquaprotect, FOEN)"),
    "ch.bafu.aquaprotect_100": (2, "Flood area, 100-year (Aquaprotect, FOEN)"),
}
HAIL_SOURCE = "Hail size, 50-year return period (MeteoSwiss)"
LEVEL_WORDS = {0: "low", 1: "medium", 2: "high"}


class MapError(Exception):
    """A map or address service did not answer."""


class AddressNotFound(Exception):
    pass


def lv95(lat: float, lon: float) -> tuple:
    """WGS84 -> Swiss LV95 (E, N), swisstopo's published approximation (about 1 m)."""
    p = (lat * 3600 - 169028.66) / 10000
    l = (lon * 3600 - 26782.5) / 10000
    e = 2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p - 44.54 * l ** 3
    n = (1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p
         - 194.56 * l * l * p + 119.79 * p ** 3)
    return e, n


def _get(url: str, params: dict, as_json: bool):
    key = cache.make_key(url, sorted(params.items()))
    hit = cache.get("geo", key)
    if hit is not None:
        return hit
    try:
        r = requests.get(url, params=params, timeout=settings.HTTP_TIMEOUT_S)
        r.raise_for_status()
        value = r.json() if as_json else r.text
    except (requests.RequestException, ValueError) as exc:
        raise MapError(str(exc)) from exc
    cache.put("geo", key, value)
    return value


def geocode(address: str) -> dict:
    data = _get(SEARCH, {"searchText": address, "type": "locations", "limit": 1}, True)
    results = data.get("results") or []
    if not results:
        raise AddressNotFound(address)
    attrs = results[0]["attrs"]
    lat, lon = float(attrs["lat"]), float(attrs["lon"])
    e, n = lv95(lat, lon)
    label = re.sub(r"<[^>]+>", "", attrs.get("label") or address).strip()
    return {"label": label, "lat": lat, "lon": lon, "e": round(e, 1), "n": round(n, 1)}


def suggest(text: str, limit: int = 6) -> list:
    if len(text.strip()) < 3:
        return []
    data = _get(SEARCH, {"searchText": text, "type": "locations", "limit": limit}, True)
    labels = [re.sub(r"<[^>]+>", "", (r.get("attrs") or {}).get("label", "")).strip()
              for r in data.get("results") or []]
    return [x for x in dict.fromkeys(labels) if x]


def parse_feature_info(text: str) -> dict:
    """MapServer's text answer -> {layer id: [ {attribute: value}, ... ]}.

        Layer 'ch.x'
          Feature 0:
            ch.x.value_0.name = '3.5'
    """
    found, layer = {}, None
    for raw in (text or "").splitlines():
        line = raw.strip()
        m = re.match(r"Layer '([^']+)'", line)
        if m:
            layer = m.group(1)
            continue
        if layer and re.match(r"Feature \S+:", line):
            found.setdefault(layer, []).append({})
            continue
        m = re.match(r"(\S+) = '(.*)'$", line)
        if m and layer and found.get(layer):
            name = m.group(1)
            if name.startswith(layer + "."):
                name = name[len(layer) + 1:]
            if name.endswith(".name"):
                name = name[:-5]
            found[layer][-1][name] = m.group(2)
    return found


def _hail_cm(features: list):
    for attrs in features:
        for name in ("value_0", "value"):
            try:
                return float(attrs[name])
            except (KeyError, TypeError, ValueError):
                continue
    return None


def levels_from_answer(found: dict) -> dict:
    """Pure function (testable offline): parsed WMS answer -> hazard result."""
    hail = {"level": 0, "available": True, "sources": [HAIL_SOURCE], "value": None}
    cm = _hail_cm(found.get(HAIL_LAYER, []))
    if cm is None:
        # The hail map covers all of Switzerland, so no value means "no answer".
        hail.update(available=False, sources=["Hail map did not answer for this point"])
    else:
        if cm > 15:          # value in mm instead of cm
            cm /= 10
        hail["value"] = f"{cm:g} cm hailstones (50-year)"
        hail["level"] = 2 if cm >= HAIL_CUTOFFS_CM[1] else 1 if cm >= HAIL_CUTOFFS_CM[0] else 0

    water = {"level": 0, "available": True, "sources": [], "value": "not inside a mapped flood zone"}
    zones = []
    for layer, (level, source) in WATER_LAYERS.items():
        if found.get(layer):
            water["level"] = max(water["level"], level)
            zones.append(source)
    water["sources"] = zones or [s for _, s in WATER_LAYERS.values()]
    if zones:
        water["value"] = "inside: " + "; ".join(zones)
    return {"hail": hail, "water": water}


def unavailable() -> dict:
    gone = {"level": 0, "available": False, "sources": ["Hazard map did not answer"], "value": None}
    return {"hail": dict(gone), "water": dict(gone)}


def simulated(hail: int, water: int) -> dict:
    out = {}
    for name, lvl in (("hail", hail), ("water", water)):
        out[name] = {"level": int(lvl), "available": True, "simulated": True,
                     "sources": ["Simulated level (set on the details page)"],
                     "value": f"simulated level {int(lvl)}"}
    return out


def read_hazards(e: float, n: float) -> dict:
    layers = ",".join([HAIL_LAYER, *WATER_LAYERS])
    params = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo",
        "LAYERS": layers, "QUERY_LAYERS": layers, "STYLES": "", "CRS": "EPSG:2056",
        # 100 m square, 101 pixels: the address is the centre pixel (about 1 m).
        "BBOX": f"{e - 50:.1f},{n - 50:.1f},{e + 50:.1f},{n + 50:.1f}",
        "WIDTH": 101, "HEIGHT": 101, "I": 50, "J": 50,
        "INFO_FORMAT": "text/plain", "FEATURE_COUNT": 5,
    }
    return levels_from_answer(parse_feature_info(_get(WMS, params, False)))

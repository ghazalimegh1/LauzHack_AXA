"""Address -> Swiss coordinates -> what the official hazard maps say at that point.
Uses the free federal geo API (api3.geo.admin.ch). No AI, no cost per request."""
from __future__ import annotations

import re

import requests

from . import cache, config

API = "https://api3.geo.admin.ch/rest/services/api"


class GeoError(Exception):
    pass


def wgs84_to_lv95(lat: float, lon: float) -> tuple[float, float]:
    """swisstopo's approximate formula (about 1 m accuracy).
    We convert ourselves instead of trusting the API's x/y fields, whose order
    was swapped in a 2025 API release."""
    phi = (lat * 3600 - 169028.66) / 10000
    lam = (lon * 3600 - 26782.5) / 10000
    e = (2600072.37 + 211455.93 * lam - 10938.51 * lam * phi
         - 0.36 * lam * phi ** 2 - 44.54 * lam ** 3)
    n = (1200147.07 + 308807.95 * phi + 3745.25 * lam ** 2 + 76.63 * phi ** 2
         - 194.56 * lam ** 2 * phi + 119.79 * phi ** 3)
    return e, n


def _get(url: str, params: dict) -> dict:
    k = cache.key(url, repr(sorted(params.items())))
    hit = cache.get("geo", k)
    if hit is not None:
        return hit
    try:
        r = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeoError(str(exc)) from exc
    cache.put("geo", k, data)
    return data


def geocode(address: str) -> dict:
    data = _get(f"{API}/SearchServer",
                {"searchText": address, "type": "locations", "limit": 1})
    results = data.get("results") or []
    if not results:
        raise GeoError(f"Address not found: {address!r}")
    a = results[0]["attrs"]
    lat, lon = float(a["lat"]), float(a["lon"])
    e, n = wgs84_to_lv95(lat, lon)
    label = re.sub(r"<[^>]+>", "", a.get("label", address))  # the API wraps parts in <b>
    return {"label": label, "lat": lat, "lon": lon, "e": e, "n": n}


def identify(e: float, n: float, layer_ids: list[str]) -> list[dict]:
    """Which features of these layers lie exactly on the point.
    UNUSED since 2026-11-21: this REST endpoint answers 400 "No GeoTable was found" for our
    raster hazard layers, so hazards.py asks the WMS (GetFeatureInfo) instead. Kept for reference."""
    data = _get(f"{API}/MapServer/identify", {
        "geometry": f"{e:.1f},{n:.1f}",
        "geometryType": "esriGeometryPoint",
        "sr": 2056,
        "layers": "all:" + ",".join(layer_ids),
        "tolerance": 0,
        "mapExtent": f"{e - 50:.0f},{n - 50:.0f},{e + 50:.0f},{n + 50:.0f}",
        "imageDisplay": "100,100,96",
        "returnGeometry": "false",
        "lang": "en",
    })
    return data.get("results") or []

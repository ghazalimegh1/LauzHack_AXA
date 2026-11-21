"""The next storm at the site, from the free Open-Meteo forecast (next 48 hours). No AI.

A storm hour is an hour with a thunderstorm (weather codes 95-99) or gusts of at least
50 km/h. Code 96 means thunderstorm with slight hail, 99 with heavy hail.
Severity is our own simple three-step rule (see `severity`).
"""
from __future__ import annotations

import time

import requests

from . import settings

API = "https://api.open-meteo.com/v1/forecast"
HOURS = 48
GUSTS_STORM_KMH = 50
KEEP_S = 600                 # reuse a forecast for 10 minutes
_memory: dict = {}


def severity(hail: str, gust: float, thunder: bool) -> str:
    if hail == "heavy" or gust >= 89:
        return "severe"
    if hail == "slight" or gust >= 62:
        return "strong"
    if thunder or gust >= GUSTS_STORM_KMH:
        return "moderate"
    return "none"


def next_storm(hourly: dict) -> dict:
    """Pure function: Open-Meteo hourly lists -> the first storm, or storm=None."""
    rows = list(zip(hourly.get("time", []), hourly.get("weather_code", []),
                    hourly.get("wind_gusts_10m", []), hourly.get("precipitation", [])))

    def stormy(row) -> bool:
        return (row[1] or 0) >= 95 or (row[2] or 0) >= GUSTS_STORM_KMH

    first = next((i for i, r in enumerate(rows) if stormy(r)), None)
    if first is None:
        return {"storm": None, "hours": len(rows)}
    last = first
    while last + 1 < len(rows) and stormy(rows[last + 1]):
        last += 1
    window = rows[first:last + 1]
    codes = [r[1] or 0 for r in window]
    gust = max(r[2] or 0 for r in window)
    hail = "heavy" if 99 in codes else "slight" if 96 in codes else "none"
    thunder = max(codes) >= 95
    kind = "hail storm" if hail != "none" else "thunderstorm" if thunder else "wind storm"
    return {"hours": len(rows), "storm": {
        "kind": kind,
        "starts": int(window[0][0]),
        "ends": int(window[-1][0]) + 3600,
        "severity": severity(hail, gust, thunder),
        "hail": hail,
        "gust_kmh": round(gust),
        "rain_mm": round(sum(r[3] or 0 for r in window), 1),
    }}


def forecast(lat: float, lon: float) -> dict:
    key = (round(lat, 3), round(lon, 3))
    hit = _memory.get(key)
    if hit and time.time() - hit[0] < KEEP_S:
        return hit[1]
    r = requests.get(API, params={
        "latitude": lat, "longitude": lon, "timeformat": "unixtime",
        "forecast_hours": HOURS, "wind_speed_unit": "kmh",
        "hourly": "weather_code,wind_gusts_10m,precipitation",
    }, timeout=settings.HTTP_TIMEOUT_S)
    r.raise_for_status()
    out = {**next_storm(r.json().get("hourly") or {}), "source": "Open-Meteo",
           "fetched": int(time.time())}
    _memory[key] = (time.time(), out)
    return out

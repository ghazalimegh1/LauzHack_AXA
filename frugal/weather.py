"""When is the next storm or hail storm expected at the site, and how bad will it be?

Source: the free Open-Meteo forecast API (no key, no cost), hourly for the next 48 hours.
No AI. The website turns the start time into a live countdown.

A "storm hour" is an hour with a thunderstorm in the forecast (WMO weather codes 95-99)
or wind gusts of at least 50 km/h (Beaufort 7, "near gale"). Hail comes from the weather
code: 96 = thunderstorm with slight hail, 99 = with heavy hail (Open-Meteo only forecasts
hail in Central Europe, which includes Switzerland).
"""
from __future__ import annotations

import time

import requests

from . import config

API = "https://api.open-meteo.com/v1/forecast"
HOURS = 48
GUST_STORM = 50          # km/h, Beaufort 7
KEEP_S = 600             # a forecast is reused for 10 minutes, then fetched again
THUNDER, SLIGHT_HAIL, HEAVY_HAIL = 95, 96, 99
_memo: dict = {}         # (lat, lon) -> (fetched at, forecast); in memory, not on disk,
                         # because forecasts go out of date (the disk cache never expires)


def _wind_name(gust: float) -> str:
    # Beaufort scale names for the strongest gust.
    for floor, name in ((89, "storm-force gusts"), (75, "strong gale gusts"),
                        (62, "gale-force gusts"), (50, "strong gusts")):
        if gust >= floor:
            return name
    return "light wind"


def _severity(hail: str, gust: float, thunder: bool) -> str:
    """Three steps, our own simple rule: Severe / Strong / Moderate."""
    if hail == "heavy" or gust >= 89:
        return "severe"
    if hail == "slight" or gust >= 62:
        return "strong"
    return "moderate" if thunder or gust >= GUST_STORM else "none"


def summarise(hourly: dict) -> dict:
    """Pure function, so it can be tested without the internet.
    hourly: Open-Meteo's lists 'time' (unix seconds), 'weather_code', 'wind_gusts_10m',
    'precipitation'. Returns the first storm in the window, or storm=None."""
    rows = list(zip(hourly["time"], hourly["weather_code"],
                    hourly["wind_gusts_10m"], hourly["precipitation"]))
    stormy = lambda r: (r[1] or 0) >= THUNDER or (r[2] or 0) >= GUST_STORM  # noqa: E731
    start = next((i for i, r in enumerate(rows) if stormy(r)), None)
    if start is None:
        return {"storm": None, "hours": len(rows)}
    end = start
    while end + 1 < len(rows) and stormy(rows[end + 1]):
        end += 1
    window = rows[start:end + 1]
    codes = [r[1] or 0 for r in window]
    gust = max(r[2] or 0 for r in window)
    hail = "heavy" if HEAVY_HAIL in codes else "slight" if SLIGHT_HAIL in codes else "none"
    thunder = max(codes) >= THUNDER
    kind = "hail storm" if hail != "none" else "thunderstorm" if thunder else "wind storm"
    return {"hours": len(rows), "storm": {
        "kind": kind, "starts": window[0][0], "ends": window[-1][0] + 3600,
        "severity": _severity(hail, gust, thunder), "hail": hail,
        "gust_kmh": round(gust), "wind": _wind_name(gust),
        "rain_mm": round(sum(r[3] or 0 for r in window), 1)}}


def forecast(lat: float, lon: float) -> dict:
    """The next storm near this point. Raises requests.RequestException if the service is down."""
    key = (round(lat, 3), round(lon, 3))
    hit = _memo.get(key)
    if hit and time.time() - hit[0] < KEEP_S:
        return hit[1]
    r = requests.get(API, params={
        "latitude": lat, "longitude": lon, "timeformat": "unixtime", "forecast_hours": HOURS,
        "hourly": "weather_code,wind_gusts_10m,precipitation", "wind_speed_unit": "kmh",
    }, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    out = {**summarise(r.json()["hourly"]), "source": "Open-Meteo", "fetched": int(time.time())}
    _memo[key] = (time.time(), out)
    return out

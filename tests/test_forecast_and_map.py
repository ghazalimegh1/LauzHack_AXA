"""Storm forecast parsing and hazard map reading, without the internet."""
from sitecheck import forecast, hazard_map

H = 3600


def hourly(codes, gusts, rain=None):
    n = len(codes)
    return {"time": [1_000_000 + i * H for i in range(n)], "weather_code": codes,
            "wind_gusts_10m": gusts, "precipitation": rain or [0.5] * n}


def test_no_storm():
    out = forecast.next_storm(hourly([1, 2, 3], [10, 20, 30]))
    assert out["storm"] is None and out["hours"] == 3


def test_hail_storm_window():
    out = forecast.next_storm(hourly([1, 95, 99, 96, 3], [20, 40, 70, 55, 10], [0, 2, 5, 1, 0]))
    s = out["storm"]
    assert s["kind"] == "hail storm" and s["hail"] == "heavy" and s["severity"] == "severe"
    assert s["starts"] == 1_000_000 + H and s["ends"] == 1_000_000 + 4 * H
    assert s["gust_kmh"] == 70 and s["rain_mm"] == 8.0


def test_thunderstorm_and_wind_storm():
    assert forecast.next_storm(hourly([95], [30]))["storm"]["kind"] == "thunderstorm"
    wind = forecast.next_storm(hourly([3, 3], [10, 65]))["storm"]
    assert wind["kind"] == "wind storm" and wind["severity"] == "strong"
    assert forecast.next_storm(hourly([96], [10]))["storm"]["severity"] == "strong"
    assert forecast.next_storm(hourly([95], [10]))["storm"]["severity"] == "moderate"


def test_missing_values_are_tolerated():
    out = forecast.next_storm(hourly([None, 95], [None, None], [None, None]))
    assert out["storm"]["kind"] == "thunderstorm"


WMS_TEXT = """GetFeatureInfo results:

Layer 'ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre'
  Feature 0:
    ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre.value_0.name = '3.5'
Layer 'ch.bafu.aquaprotect_500'
  Feature 12:
"""


def test_map_answer_to_levels():
    found = hazard_map.parse_feature_info(WMS_TEXT)
    out = hazard_map.levels_from_answer(found)
    assert out["hail"]["level"] == 1 and out["hail"]["available"]
    assert out["water"]["level"] == 1 and "500-year" in out["water"]["value"]


def test_big_hail_is_level_2_and_no_hail_answer_is_unavailable():
    big = hazard_map.parse_feature_info(WMS_TEXT.replace("'3.5'", "'4.5'"))
    assert hazard_map.levels_from_answer(big)["hail"]["level"] == 2
    none = hazard_map.levels_from_answer({})
    assert none["hail"]["available"] is False          # never "low" when the map is silent
    assert none["water"]["available"] is True and none["water"]["level"] == 0


def test_lv95_conversion_is_close():
    e, n = hazard_map.lv95(46.51936, 6.57868)      # Route Cantonale 11, Lausanne
    assert abs(e - 2534010) < 5 and abs(n - 1152370) < 5

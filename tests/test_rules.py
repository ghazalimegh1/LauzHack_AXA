"""Importance, labels, what the AI is asked for, uncertain findings and the site action."""
from sitecheck import catalogue, rules


def finding(kind, conf=0.9, source="cheap model", t=1.0, frame=0, fid=0):
    return {"id": fid, "kind": kind, "confidence": conf, "source": source, "t": t,
            "frame": frame, "box": [0.1, 0.1, 0.3, 0.3]}


def hazards(hail=1, water=1, available=True):
    return {"hail": {"level": hail, "available": available},
            "water": {"level": water, "available": available}}


def test_importance_is_weight_times_level():
    assert catalogue.importance("ramp_down", {"hail": 0, "water": 2}) == 6
    assert catalogue.importance("ground_door", {"hail": 2, "water": 1}) == 2
    assert catalogue.importance("outdoor_goods", {"hail": 0, "water": 2}) == 0


def test_labels():
    assert catalogue.label(8) == "high"
    assert catalogue.label(4) == "high"
    assert catalogue.label(3) == "medium"
    assert catalogue.label(2) == "medium"
    assert catalogue.label(1) == "low"
    assert catalogue.label(0) == "not relevant here"


def test_vehicle_is_high_wherever_hail_is_at_least_medium():
    assert catalogue.label(catalogue.importance("vehicle", {"hail": 1})) == "high"
    assert catalogue.label(catalogue.importance("vehicle", {"hail": 0})) == "not relevant here"


def test_map_decides_what_the_ai_looks_for():
    kinds = catalogue.kinds_to_ask({"hail": 1, "water": 0}, detector_on=True)
    assert set(kinds) == {"outdoor_goods"}
    assert "vehicle" in catalogue.kinds_to_ask({"hail": 1, "water": 0}, detector_on=False)
    assert catalogue.kinds_to_ask({"hail": 0, "water": 0}, detector_on=True) == []
    water = catalogue.kinds_to_ask({"hail": 0, "water": 2}, detector_on=True)
    assert set(water) == {"basement_opening", "ground_door", "ramp_down", "critical_equipment_low"}


def test_low_confidence_is_uncertain_and_not_counted():
    lv = {"hail": 2, "water": 0}
    sure = rules.score_finding(finding("outdoor_goods", 0.8), lv)
    unsure = rules.score_finding(finding("outdoor_goods", 0.4), lv)
    assert sure["counted"] and not sure["uncertain"]
    assert unsure["uncertain"] and not unsure["counted"]
    # the local detector has its own, lower bar
    assert rules.score_finding(finding("vehicle", 0.55, "local detector"), lv)["counted"]


def test_weak_points_group_by_kind_and_keep_uncertain_apart():
    lv = {"hail": 1, "water": 1}
    found = [rules.score_finding(f, lv) for f in [
        finding("vehicle", 0.9, "local detector", t=3, fid=0),
        finding("vehicle", 0.8, "local detector", t=9, fid=1),
        finding("outdoor_goods", 0.3, t=5, fid=2),
        finding("ramp_down", 0.9, t=7, fid=3),
    ]]
    points = rules.weak_points(found, lv)
    names = [p["kind"] for p in points]
    assert names[0] == "vehicle" and points[0]["count"] == 2 and points[0]["seen_at"] == [3, 9]
    goods = next(p for p in points if p["kind"] == "outdoor_goods")
    assert goods["status"] == "uncertain"
    assert names[-1] == "outdoor_goods"                # uncertain ones come last


def test_site_action():
    lv = {"hail": 1, "water": 1}
    high = rules.weak_points([rules.score_finding(finding("vehicle", 0.9, "local detector"), lv)], lv)
    assert rules.decide(high, hazards())["text"] == "Propose an on-site prevention check"
    med = rules.weak_points([rules.score_finding(finding("ramp_down", 0.9), lv)], lv)
    assert rules.decide(med, hazards())["text"] == "Send targeted prevention tips"
    unsure = rules.weak_points([rules.score_finding(finding("outdoor_goods", 0.2), lv)], lv)
    assert rules.decide(unsure, hazards())["text"] == "No action needed"
    assert rules.decide([], hazards(available=False))["key"] == "unknown"

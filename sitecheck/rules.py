"""Plain rules that turn findings into a decision. No AI here.

- importance = weight x hazard level at the address
- label: high >= 4, medium >= 2, low >= 1, otherwise "not relevant here"
- a low-confidence finding is "uncertain": shown, but not counted
- site action: any counted "high" -> on-site prevention check;
               anything else counted -> targeted prevention tips; nothing -> no action
"""
from __future__ import annotations

from . import catalogue, settings

ACTIONS = {
    "check": {"text": "Propose an on-site prevention check",
              "headline": "Have your site checked before the next storm"},
    "tips": {"text": "Send targeted prevention tips",
             "headline": "A few simple steps will protect your site"},
    "none": {"text": "No action needed",
             "headline": "Nothing at your site needs attention right now"},
    "unknown": {"text": "No decision possible",
                "headline": "We could not read the hazard map for this address"},
}
DETECTOR_UNSURE_BELOW = 0.5


def score_finding(f: dict, levels: dict) -> dict:
    score = catalogue.importance(f["kind"], levels)
    limit = DETECTOR_UNSURE_BELOW if f["source"] == "local detector" else settings.UNSURE_BELOW
    uncertain = f["confidence"] < limit
    lab = catalogue.label(score)
    return {**f, "score": score, "label": lab, "uncertain": uncertain,
            "counted": (not uncertain) and lab != catalogue.NOT_RELEVANT}


def weak_points(findings: list, levels: dict) -> list:
    """One weak point per kind of thing (e.g. all parked cars together)."""
    by_kind = {}
    for f in findings:
        if f["label"] == catalogue.NOT_RELEVANT:
            continue
        by_kind.setdefault(f["kind"], []).append(f)
    out = []
    for kind, items in by_kind.items():
        sure = [f for f in items if not f["uncertain"]]
        pool = sure or items
        best = max(pool, key=lambda f: (f["confidence"], -f["t"]))
        item = catalogue.KINDS[kind]
        out.append({
            "kind": kind, "name": item["name"], "hazard": item["hazard"],
            "level": int(levels.get(item["hazard"], 0)),
            "score": best["score"], "label": best["label"],
            "status": "counted" if sure else "uncertain",
            "count": len(sure) if sure else len(items),
            "confidence": round(best["confidence"], 2),
            "best": best["id"], "frame": best["frame"], "t": best["t"],
            # the clearest recognisable close-up (None: show the label without a picture)
            "photo": next((f["id"] for f in sorted(pool, key=lambda f: -f["confidence"])
                           if f.get("photo", True)), None),
            # the plain names the AI used, e.g. "pallets, machine"
            "details": sorted({f["detail"] for f in pool if f.get("detail")}),
            "seen_at": sorted({round(f["t"], 1) for f in pool}),
            # one entry per key frame: things standing side by side in one picture share an
            # entry, things seen in different pictures (e.g. other cars) each get their own
            "sightings": _sightings(pool),
            "source": best["source"],
            "why": item["why"], "now": item["now"], "later": item["later"],
        })
    out.sort(key=lambda w: (w["status"] != "counted", -w["score"], -w["confidence"]))
    return out


def _sightings(pool: list) -> list:
    frames = {}
    for f in pool:
        frames.setdefault(f["frame"], []).append(f)
    # "box" spans all of them, so the page can centre the picture on the cars
    return [{"frame": fr, "t": min(f["t"] for f in fs), "count": len(fs),
             "details": sorted({f["detail"] for f in fs if f.get("detail")}),
             "box": [min(f["box"][0] for f in fs), min(f["box"][1] for f in fs),
                     max(f["box"][2] for f in fs), max(f["box"][3] for f in fs)]}
            for fr, fs in sorted(frames.items(), key=lambda kv: min(f["t"] for f in kv[1]))]


def decide(points: list, hazards: dict) -> dict:
    if not any(h.get("available") for h in hazards.values()):
        key = "unknown"
    else:
        counted = [w for w in points if w["status"] == "counted"]
        if any(w["label"] == "high" for w in counted):
            key = "check"
        elif counted:
            key = "tips"
        else:
            key = "none"
    return {"key": key, **ACTIONS[key]}

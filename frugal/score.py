"""Plain rules, no AI: the same inputs always give the same score, and an
underwriter can read exactly why. Per hazard group:  score = area_level * (1 + weak_points)."""
from __future__ import annotations

from .checklist import BY_ID

ACTIONS = [  # (minimum score, action for AXA)
    (4, "Propose an on-site prevention check"),
    (1, "Send targeted prevention tips"),
    (0, "No action needed"),
]


def evaluate(hazards: dict, answers: dict) -> dict:
    groups = {}
    for g, h in hazards.items():
        weak = [i for i, a in answers.items() if a == "y" and BY_ID[i]["group"] == g]
        unclear = [i for i, a in answers.items() if a == "u" and BY_ID[i]["group"] == g]
        groups[g] = {"area": h["level"], "weak": weak, "unclear": unclear,
                     "score": h["level"] * (1 + len(weak))}
    top = max(v["score"] for v in groups.values())
    action = next(a for threshold, a in ACTIONS if top >= threshold)
    tips = [BY_ID[i]["tip"] for v in groups.values() for i in v["weak"]]
    if any(v["unclear"] and v["area"] == 2 for v in groups.values()):
        tips.append("Some weak points were not visible: a second photo from another side would help.")
    return {"groups": groups, "score": top, "action": action, "tips": tips}

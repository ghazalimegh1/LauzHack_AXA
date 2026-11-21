"""The core idea: the map decides what the camera looks for.
Each question belongs to one hazard group and is only asked when that group is
at least 'medium' at the address. Fewer questions -> fewer tokens -> cheaper."""
from __future__ import annotations

QUESTIONS = [
    # --- water: river floods and surface runoff enter through low openings ---
    {"id": "light_well", "group": "water",
     "q": "Is there a basement window or light well at or below ground level?",
     "tip": "Fit a raised rim or a watertight cover on basement windows and light wells."},
    {"id": "door_low", "group": "water",
     "q": "Is an entrance or garage door at ground level with no step up?",
     "tip": "Keep mobile flood barriers ready, or raise the threshold of low doors."},
    {"id": "ramp_down", "group": "water",
     "q": "Is there a driveway or ramp sloping down towards the building?",
     "tip": "Add a drainage channel at the bottom of the ramp and a backflow valve."},
    {"id": "slope_to_house", "group": "water",
     "q": "Does the surrounding ground slope towards the building?",
     "tip": "Redirect runoff away from the walls (small berm or regraded ground)."},
    # --- hail: glass, blinds and cars are the typical hail claims ---
    {"id": "glass_roof", "group": "hail",
     "q": "Are skylights, solar panels or glass roofing visible?",
     "tip": "Choose hail-resistant glazing and panels (check the hail resistance class)."},
    {"id": "blinds", "group": "hail",
     "q": "Are external blinds, shutters or awnings visible?",
     "tip": "Retract external blinds when MeteoSwiss warns of hail (can be automated)."},
    {"id": "car_outside", "group": "hail",
     "q": "Is a car parked outdoors without a roof over it?",
     "tip": "Park under cover when a hail warning is issued."},
]

BY_ID = {q["id"]: q for q in QUESTIONS}


def select(hazards: dict) -> list[dict]:
    return [q for q in QUESTIONS if hazards[q["group"]]["level"] >= 1]

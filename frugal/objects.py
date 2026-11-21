"""What we look for on a business site, and how much each thing matters.

importance = weight x area hazard level (0-2), so 0..6:
  weight  3 = typical large claim (vehicles, glass, basement openings, critical equipment low)
          2 = moderate claim (solar panels, blinds, outdoor goods, low doors)
  level   comes from the official map for this address
The same object therefore matters a lot in a hail zone and not at all where hail is rare.
Weights are our team's assumption, written down so AXA can tune them.
"""
from __future__ import annotations

CATALOGUE = {
    # ---------------- hail ----------------
    "vehicle": {
        "group": "hail", "weight": 3, "name": "vehicle parked outside",
        "find": "car, van, truck or motorbike parked outdoors with no roof over it",
        "why": "Hail dents and breaks parked cars; repairs are costly and many cars are hit at once.",
        "now": "Move vehicles into a garage or under a roof.",
        "later": "Plan covered parking or hail nets for the car park."},
    "glass_roof": {
        "group": "hail", "weight": 3, "name": "skylight / glass roof",
        "find": "skylight, glass roof, glass canopy or greenhouse glazing",
        "why": "Large glass surfaces break under big hailstones; water then enters.",
        "now": "Close skylights and move people and valuables away from glass roofs.",
        "later": "Use hail-resistant glazing (check its hail resistance class)."},
    "solar_panel": {
        "group": "hail", "weight": 2, "name": "solar panels",
        "find": "solar or photovoltaic panels on a roof or facade",
        "why": "Panels are exposed and expensive; hail cracks the glass surface.",
        "now": "Photograph the panels now to document their condition for any claim.",
        "later": "Choose panels with a high hail resistance class at the next renewal."},
    "external_blinds": {
        "group": "hail", "weight": 2, "name": "external blinds / awnings",
        "find": "external slat blinds, roller shutters or fabric awnings",
        "why": "Hail rarely breaks windows but often damages extended blinds.",
        "now": "Retract external blinds and awnings fully.",
        "later": "Automate blind retraction on hail warnings."},
    "outdoor_goods": {
        "group": "hail", "weight": 2, "name": "goods or machines outside",
        "find": "pallets, stored goods, containers, machines or equipment standing outdoors",
        "why": "Stock and machines left outside are damaged by hail and heavy rain.",
        "now": "Move goods and machines inside or cover them with tarpaulins.",
        "later": "Create a covered storage area."},
    # ---------------- water ----------------
    "basement_opening": {
        "group": "water", "weight": 3, "name": "basement window / light well",
        "find": "basement window, light well or ventilation opening at or below ground level",
        "why": "Surface water flows into basements through low openings first.",
        "now": "Close basement windows and block light wells with sandbags or boards.",
        "later": "Raise light-well rims or fit watertight covers."},
    "ground_door": {
        "group": "water", "weight": 2, "name": "door at ground level",
        "find": "entrance, loading door or garage door at ground level with no step up",
        "why": "Doors without a threshold let water in during heavy rain.",
        "now": "Put mobile flood barriers in front of low doors.",
        "later": "Raise thresholds or install permanent mounts for flood barriers."},
    "ramp_down": {
        "group": "water", "weight": 3, "name": "ramp down to underground garage",
        "find": "driveway or ramp sloping down into an underground garage or basement",
        "why": "Ramps funnel runoff straight into underground garages.",
        "now": "Move vehicles out of the underground garage.",
        "later": "Add a drainage channel, a backflow valve or an automatic flood gate."},
    "critical_equipment_low": {
        "group": "water", "weight": 3, "name": "critical equipment low",
        "find": "server rack, control cabinet, electrical panel or heating unit standing on the floor",
        "why": "Flooded control or server rooms can stop operations, not just damage equipment.",
        "now": "Lift portable equipment off the floor and back up data.",
        "later": "Move critical equipment above the expected water level."},
    # ---------------- privacy (never sent, never scored) ----------------
    "person": {
        "group": "privacy", "weight": 0, "name": "person",
        "find": "", "why": "Blurred on this device before any frame is sent.",
        "now": "", "later": ""},
}

LEVELS = [(4, "high"), (2, "medium"), (1, "low"), (0, "not relevant here")]


def importance(kind: str, hazards: dict) -> tuple[int, str]:
    item = CATALOGUE[kind]
    if item["group"] not in hazards:
        return 0, "privacy"
    score = item["weight"] * hazards[item["group"]]["level"]
    return score, next(label for floor, label in LEVELS if score >= floor)


def to_ask(hazards: dict, skip: set[str] = frozenset()) -> list[str]:
    """The map decides what the model looks for: only groups with level >= 1,
    and nothing the free local detector already handles."""
    return [k for k, v in CATALOGUE.items()
            if v["group"] in hazards and hazards[v["group"]]["level"] >= 1 and k not in skip]

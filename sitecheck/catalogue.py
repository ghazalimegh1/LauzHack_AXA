"""What we look for on a business site, how much each thing matters, and what to do.

importance = weight x hazard level at the address (level 0, 1 or 2).
The weights are our team's assumption, written down here so an insurer can tune them.
"layer" tells the spatial view where the thing usually sits on a building.
"""
from __future__ import annotations

KINDS = {
    # ---------- hail ----------
    "vehicle": dict(
        hazard="hail", weight=4, layer="ground", name="Vehicle parked outside",
        find="car, van, truck or motorbike parked in the open",
        why="Hail dents and breaks parked vehicles, and many are hit at the same time.",
        now="Move vehicles into a garage or under a roof.",
        later="Plan covered parking or hail nets for the car park."),
    "glass_roof": dict(
        hazard="hail", weight=3, layer="roof", name="Skylight / glass roof",
        find="skylight, glass roof, glass canopy or greenhouse glass",
        why="Large hailstones break glass roofs, and rain then gets inside.",
        now="Close skylights and keep people and valuable items away from glass roofs.",
        later="Replace with hail-resistant glazing when the roof is renewed."),
    "solar_panel": dict(
        hazard="hail", weight=2, layer="roof", name="Solar panels",
        find="solar or photovoltaic panels on a roof, facade or carport",
        why="Panels are exposed and costly; hail cracks their glass surface.",
        now="Take dated photos of the panels so their condition is documented.",
        later="Choose panels with a high hail resistance class at the next renewal."),
    "external_blinds": dict(
        hazard="hail", weight=2, layer="wall", name="External blinds / awnings",
        find="external slat blinds, roller shutters or fabric awnings",
        why="Extended blinds and awnings are easily torn or dented by hail.",
        now="Pull in all external blinds and awnings.",
        later="Let the blinds retract automatically when a hail warning comes in."),
    "outdoor_goods": dict(
        hazard="hail", weight=2, layer="ground", name="Goods or machines outside",
        find="pallets, stored goods, containers, machines or equipment standing outdoors",
        why="Stock and machines left in the open are damaged by hail and heavy rain.",
        now="Bring goods and machines inside, or cover them with tarpaulins.",
        later="Set up a covered storage area."),
    # ---------- water ----------
    "basement_opening": dict(
        hazard="water", weight=3, layer="wall_base", name="Basement window / light well",
        find="basement window, light well or vent opening at or below ground level",
        why="Surface water reaches the basement through low openings first.",
        now="Close basement windows and block light wells with boards or sandbags.",
        later="Raise the rims of light wells or fit watertight covers."),
    "ground_door": dict(
        hazard="water", weight=2, layer="wall_base", name="Door at ground level",
        find="entrance, loading door or garage door at ground level with no step up",
        why="Doors without a step let rainwater straight in.",
        now="Put mobile flood barriers in front of low doors.",
        later="Raise the thresholds or fit fixed mounts for flood barriers."),
    "ramp_down": dict(
        hazard="water", weight=3, layer="ground", name="Ramp down to underground garage",
        find="driveway or ramp sloping down into an underground garage or basement",
        why="A ramp channels runoff straight into the underground garage.",
        now="Move vehicles out of the underground garage.",
        later="Add a drainage channel and a flood gate at the top of the ramp."),
    "critical_equipment_low": dict(
        hazard="water", weight=3, layer="wall_base", name="Critical equipment low",
        find="server rack, control cabinet, electrical panel or heating unit standing on the floor",
        why="Flooded control or server rooms can stop the business, not only the machines.",
        now="Lift portable equipment off the floor and back up your data.",
        later="Move critical equipment above the expected water level."),
}

# A person is never scored. The free detector finds people so they can be blurred.
PERSON = "person"

LABELS = ((4, "high"), (2, "medium"), (1, "low"))
NOT_RELEVANT = "not relevant here"


def importance(kind: str, levels: dict) -> int:
    """weight x hazard level. levels: {"hail": 0-2, "water": 0-2}."""
    item = KINDS[kind]
    return item["weight"] * int(levels.get(item["hazard"], 0) or 0)


def label(score: int) -> str:
    for floor, name in LABELS:
        if score >= floor:
            return name
    return NOT_RELEVANT


def kinds_to_ask(levels: dict, detector_on: bool) -> list:
    """The map decides what the AI looks for: only kinds whose hazard is at least level 1
    here. Vehicles are skipped when the free detector already finds them."""
    out = []
    for kind, item in KINDS.items():
        if int(levels.get(item["hazard"], 0) or 0) < 1:
            continue
        if kind == "vehicle" and detector_on:
            continue
        out.append(kind)
    return out

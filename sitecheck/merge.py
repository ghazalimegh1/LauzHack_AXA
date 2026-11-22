"""Merge repeated finds, so one object is counted once. Free code, no AI.

Models sometimes return the same object twice in one frame (two nearly identical boxes),
and two key frames taken a moment apart can show the same object again. Counting those
twice makes a site look worse than it is. Boxes are only dropped, never moved or invented:
of each group, the box with the highest confidence is kept exactly as the model gave it.
"""
from __future__ import annotations

SAME_FRAME_IOU = 0.5     # two boxes of one kind overlapping this much in one frame = one object
SAME_FRAME_COVER = 0.8   # ...or a small box lying almost fully inside a bigger one
NEXT_FRAME_IOU = 0.3     # camera moves between frames, so a looser overlap counts there
NEXT_FRAME_GAP_S = 1.5   # only key frames this close in time can show the very same view
COPY_TOLERANCE = 0.002   # 2 units on the AI's 0-1000 scale: the "same box" to the last digit
DETECTOR = "local detector"


def _area(b: list) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersection(a: list, b: list) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def iou(a: list, b: list) -> float:
    """Overlap of two [x0, y0, x1, y1] boxes: 0 = apart, 1 = identical."""
    inter = _intersection(a, b)
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def cover(a: list, b: list) -> float:
    """How much of the smaller box lies inside the other (catches box-in-box repeats)."""
    small = min(_area(a), _area(b))
    return _intersection(a, b) / small if small > 0 else 0.0


def _same_in_frame(a: dict, b: dict) -> bool:
    if a["frame"] != b["frame"]:
        return False
    return iou(a["box"], b["box"]) >= SAME_FRAME_IOU or cover(a["box"], b["box"]) >= SAME_FRAME_COVER


def _same_next_frame(a: dict, b: dict) -> bool:
    return (a["frame"] != b["frame"] and abs(a["t"] - b["t"]) <= NEXT_FRAME_GAP_S
            and iou(a["box"], b["box"]) >= NEXT_FRAME_IOU)


def _keep_best(findings: list, same) -> tuple:
    """Highest confidence first; a find that repeats an already kept one of its kind is dropped."""
    kept, dropped = [], 0
    for f in sorted(findings, key=lambda x: -x["confidence"]):
        if any(k["kind"] == f["kind"] and same(k, f) for k in kept):
            dropped += 1
        else:
            kept.append(f)
    return kept, dropped


def merge(findings: list) -> tuple:
    """Returns (findings without repeats, in their original order; number dropped)."""
    order = {id(f): i for i, f in enumerate(findings)}
    kept, in_frame = _keep_best(findings, _same_in_frame)
    kept, next_frame = _keep_best(kept, _same_next_frame)
    kept.sort(key=lambda f: order[id(f)])
    return kept, in_frame + next_frame


def _copied(a: dict, b: dict) -> bool:
    """Same kind, same box to the digit, on a key frame that shows a different view."""
    return (a["kind"] == b["kind"] and a["frame"] != b["frame"]
            and abs(a["t"] - b["t"]) > NEXT_FRAME_GAP_S
            and max(abs(x - y) for x, y in zip(a["box"], b["box"])) <= COPY_TOLERANCE)


def drop_copies(findings: list) -> tuple:
    """Drop AI boxes copied from an earlier key frame. Returns (findings, number dropped).

    Our test set showed the AI sometimes repeats its answer for one frame on a later frame,
    box for box, although the later picture shows something else. Key frames are picked
    to be different views, so a box identical to the digit is a copy, not a new find.
    The first one is kept (it is where the model looked); the local detector measures
    every frame itself, so its boxes are never treated as copies.
    """
    kept, dropped = [], 0
    for f in sorted(findings, key=lambda x: x["t"]):
        if f.get("source") != DETECTOR and any(
                k.get("source") != DETECTOR and _copied(k, f) for k in kept):
            dropped += 1
        else:
            kept.append(f)
    gone = {id(f) for f in findings} - {id(f) for f in kept}
    return [f for f in findings if id(f) not in gone], dropped

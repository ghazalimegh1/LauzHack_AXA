"""What we ask the vision models, and how their answers are read.
Prompt and parser are ported from the team's earlier frugal/vision.py (find / parse_find):
frames come first and the instructions last, keys are short to keep output tokens low,
and a broken or cut-off answer keeps every complete object instead of losing them all.
"""
from __future__ import annotations

import json
import re

import cv2
import numpy as np

from . import catalogue

_BOX_TEXT = "[ymin, xmin, ymax, xmax]"     # Gemini is trained on this order
_BOX_EXAMPLE = "[120,300,380,720]"


def jpeg(img: np.ndarray, longest: int, quality: int = 80) -> tuple:
    """Resized JPEG bytes and the (w, h) actually sent."""
    h, w = img.shape[:2]
    s = min(1.0, longest / max(h, w))
    small = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes(), (small.shape[1], small.shape[0])


def prompt(kinds: list, n: int) -> str:
    lines = "\n".join(f"{k}: {catalogue.KINDS[k]['find']}" for k in kinds)
    # 'u' is only for frames that cannot be judged: a cheap model otherwise marks every
    # clear frame with no target object as unclear, which sends all frames to the strong model.
    # 'd' names the object plainly (pallets, not "goods"), so people see what was found;
    # one short word keeps the extra output tokens tiny.
    return (f"The {n} images above are frames 0-{n - 1} of a walk-around video of a business "
            "site, checked for hail and flood prevention. Find ONLY these object types:\n"
            f"{lines}\n"
            "For each object give f = frame number, t = type, d = one plain word for it "
            "(e.g. pallets, machine, van), "
            f"b = tight box {_BOX_TEXT} scaled 0-1000 around that object only, "
            "c = confidence 0-1. Skip objects too small or blurred to name. "
            "u = list of frames too dark, blurred or blocked to judge; a clear frame without "
            "these objects is not unclear. At most 5 objects per frame. "
            "Reply with JSON only, no other text, e.g. "
            f'{{"o":[{{"f":0,"t":"glass_roof","d":"skylight","b":{_BOX_EXAMPLE},"c":0.8}}],"u":[]}}')


def parts_for(prompt_text: str, images: list) -> list:
    parts = []
    for i, img in enumerate(images):
        parts += [f"Frame {i}:", img]
    parts.append(prompt_text)
    return parts


# ---------------- reading the answer ----------------
def _json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences; take the outer {...}."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _find_json(text: str) -> dict:
    """The reply as a dict. If the JSON is broken (most often cut off at the token limit),
    keep every complete {...} object entry rather than losing the whole answer."""
    data = _json(text)
    if _pick(data, "o", "objects", "detections", "u", "unclear") is not None:
        return data
    # Also covers a bare list of objects, e.g. Gemini's own [{"box_2d": ..., "label": ...}].
    entries = [_json(m) for m in re.findall(r"\{[^{}]*\}", text or "")]
    return {"o": [e for e in entries if e]}


def _pick(d: dict, *names):
    # Models rename keys ('f' / 'frame', 'b' / 'box' / 'bbox'...); take the first one present.
    return next((d[k] for k in names if k in d), None)


def _box_numbers(b):
    """Box as [x0, y0, x1, y1] in the model's own scale, or None if unreadable."""
    if isinstance(b, dict):   # {"xmin":..} / {"x0":..} names say the axis, no order needed
        vals = [_pick(b, *ks) for ks in (("xmin", "x0"), ("ymin", "y0"),
                                         ("xmax", "x1"), ("ymax", "y1"))]
    elif isinstance(b, (list, tuple)) and len(b) == 4:
        vals = [b[1], b[0], b[3], b[2]]                     # [ymin, xmin, ymax, xmax]
    else:
        return None
    try:
        return [float(v) for v in vals]
    except (TypeError, ValueError):
        return None


def _to_fraction(box: list, size):
    """0-1 fractions, 0-1000, or pixels -> 0-1 fractions; swapped corners are put in order."""
    x0, y0, x1, y1 = box
    top = max(box)
    if top <= 1.0:
        sx = sy = 1.0                      # already fractions
    elif top <= 1000 or not size:
        sx = sy = 1000.0                   # what we asked for
    else:
        sx, sy = size                      # pixels: only detectable above 1000
    x0, x1 = sorted((x0 / sx, x1 / sx))
    y0, y1 = sorted((y0 / sy, y1 / sy))
    clamp = lambda v: min(1.0, max(0.0, v))  # noqa: E731
    out = [clamp(x0), clamp(y0), clamp(x1), clamp(y1)]
    return out if out[2] > out[0] and out[3] > out[1] else None


MIN_BOX_SIDE = 0.03   # boxes narrower or lower than 3% of the picture show nothing useful


def _big_enough(box: list) -> bool:
    return box[2] - box[0] >= MIN_BOX_SIDE and box[3] - box[1] >= MIN_BOX_SIDE


def _detail(value) -> str:
    """The model's plain name for the object, kept short and to letters only (it is shown)."""
    text = re.sub(r"[^a-z \-]", "", str(value or "").lower()).strip()
    return " ".join(text.split()[:3])[:24]


def _object(o, n: int, kinds: list, sizes):
    """One well-formed object, or None: a bad entry is dropped, never guessed."""
    if not isinstance(o, dict):
        return None
    try:
        f = int(_pick(o, "f", "frame"))
        t = str(_pick(o, "t", "type", "kind", "label"))
        c = _pick(o, "c", "conf", "confidence")
        c = 0.5 if c is None else float(c)
    except (TypeError, ValueError):
        return None
    if not (0 <= f < n and t in kinds):
        return None
    nums = _box_numbers(_pick(o, "b", "box", "bbox", "box_2d"))
    box = nums and _to_fraction(nums, sizes[f] if sizes else None)
    if not box or not _big_enough(box):
        return None
    return {"frame": f, "kind": t, "box": box, "confidence": round(min(1.0, max(0.0, c)), 2),
            "detail": _detail(_pick(o, "d", "detail", "what", "name"))}


def read_answer(text: str, kinds: list, n: int, sizes=None) -> tuple:
    """Objects as {"frame" (0-based), "kind", "box": [x0, y0, x1, y1] as 0-1 fractions,
    "confidence"}, plus the set of frames (0-based) the model could not judge."""
    data = _find_json(text)
    raw = _pick(data, "o", "objects", "detections") or []
    objs = [ob for ob in (_object(o, n, kinds, sizes) for o in raw) if ob]
    unclear = {int(u) for u in _pick(data, "u", "unclear") or []
               if str(u).strip().isdigit() and int(u) < n}
    return objs, unclear

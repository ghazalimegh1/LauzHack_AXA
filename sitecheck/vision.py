"""What we ask the vision models, and how their answers are read."""
from __future__ import annotations

import cv2
import numpy as np

from . import catalogue


def jpeg(img: np.ndarray, longest: int, quality: int = 80) -> tuple:
    """Resized JPEG bytes and the (w, h) actually sent."""
    h, w = img.shape[:2]
    s = min(1.0, longest / max(h, w))
    small = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes(), (small.shape[1], small.shape[0])


def prompt(kinds: list, n_frames: int) -> str:
    lines = "\n".join(f'- "{k}": {catalogue.KINDS[k]["find"]}' for k in kinds)
    return (
        f"You see {n_frames} photos from a walk around a business site. They are used for "
        "a storm-prevention check (hail and heavy rain).\n"
        f"Look ONLY for these things:\n{lines}\n\n"
        "Answer with JSON only, in this form:\n"
        '{"objects": [{"frame": 1, "type": "<one of the ids above>", '
        '"box": [ymin, xmin, ymax, xmax], "confidence": 0.0}], "unsure_frames": []}\n'
        "Rules: frame numbers start at 1. Box coordinates are 0-1000 on that photo. "
        "Report only what you can actually see; never guess. At most 4 objects per photo. "
        "confidence (0-1) says how sure you are that it is that type. Put a frame number in "
        "unsure_frames if the photo is too dark or unclear to decide. "
        'If nothing is found, answer {"objects": [], "unsure_frames": []}.'
    )


def parts_for(prompt_text: str, images: list) -> list:
    parts = [prompt_text]
    for i, img in enumerate(images, 1):
        parts += [f"Photo {i}:", img]
    return parts


def read_answer(data: dict, kinds: list, n_frames: int) -> tuple:
    """Model JSON -> (objects with 0-1 boxes [x0, y0, x1, y1], unsure frame numbers).
    Anything malformed is dropped rather than guessed."""
    objects = []
    for o in data.get("objects") or []:
        if not isinstance(o, dict) or o.get("type") not in kinds:
            continue
        try:
            frame = int(o.get("frame"))
            ymin, xmin, ymax, xmax = [min(1000.0, max(0.0, float(v))) for v in o.get("box")]
        except (TypeError, ValueError):
            continue
        if not 1 <= frame <= n_frames or xmax - xmin < 5 or ymax - ymin < 5:
            continue
        try:
            conf = float(o.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        objects.append({"frame": frame, "kind": o["type"],
                        "box": [xmin / 1000, ymin / 1000, xmax / 1000, ymax / 1000],
                        "confidence": min(1.0, max(0.0, conf))})
    unsure = set()
    for f in data.get("unsure_frames") or []:
        try:
            if 1 <= int(f) <= n_frames:
                unsure.add(int(f))
        except (TypeError, ValueError):
            continue
    return objects, unsure

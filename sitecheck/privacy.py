"""Free, local object detection (YOLO11n, 5 MB, runs on a laptop CPU in ~0.1 s per frame).
Ported from the team's earlier frugal/detect.py: same classes, same thresholds, same blur.

It only knows everyday objects (cars, trucks, people...), not skylights or light wells,
so it handles what it can and the paid model is asked only about the rest.
It also finds people, who are blurred here before any frame leaves the computer.
"""
from __future__ import annotations

import threading

import numpy as np
from PIL import Image, ImageFilter

from . import settings

# Detector class -> our catalogue type. Everything else it sees is ignored.
CLASS_MAP = {"car": "vehicle", "truck": "vehicle", "bus": "vehicle",
             "motorcycle": "vehicle", "person": "person"}
MIN_CONF = 0.35   # shown from here...
SURE = 0.5        # ...counted in the score from here

_model = None
_lock = threading.Lock()


class DetectorMissing(Exception):
    pass


def _load():
    global _model
    with _lock:
        if _model is None:  # load once; later frames reuse it
            if not settings.DETECTOR_WEIGHTS.exists():
                raise DetectorMissing(f"models/{settings.DETECTOR_WEIGHTS.name} is missing")
            from ultralytics import YOLO   # heavy import, only when first needed
            _model = YOLO(str(settings.DETECTOR_WEIGHTS))
    return _model


def _pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(img[:, :, ::-1].copy())        # OpenCV BGR -> PIL RGB


def detect(img: np.ndarray) -> list:
    """Boxes as fractions of width/height [x0, y0, x1, y1], so they fit any image size.
    Returns [{"kind": "vehicle"|"person", "label", "box", "confidence"}]."""
    pil = _pil(img)
    r = _load()(pil, verbose=False, conf=MIN_CONF)[0]
    w, h = pil.size
    out = []
    for cls, conf, box in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
        name = r.names[int(cls)]
        kind = CLASS_MAP.get(name)
        if kind:
            x0, y0, x1, y1 = box
            out.append({"kind": kind, "label": name, "box": [x0 / w, y0 / h, x1 / w, y1 / h],
                        "confidence": round(float(conf), 2)})
    return out


def blur_people(img: np.ndarray, people: list) -> np.ndarray:
    pil = _pil(img)
    w, h = pil.size
    for o in people:
        x0, y0, x1, y1 = (int(o["box"][0] * w), int(o["box"][1] * h),
                          int(o["box"][2] * w), int(o["box"][3] * h))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        region = pil.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(18))
        pil.paste(region, (x0, y0))
    return np.asarray(pil)[:, :, ::-1].copy()              # back to BGR

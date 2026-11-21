"""Free local detector (YOLO11n, runs on this computer): finds vehicles and people.
People are blurred before any image leaves the computer."""
from __future__ import annotations

import threading

import cv2
import numpy as np

from . import settings

# COCO class ids used by YOLO11n
PERSON_ID = 0
VEHICLE_IDS = {2: "car", 3: "motorbike", 5: "bus", 7: "truck"}
PERSON_MIN_CONF = 0.25     # blur generously: a missed face is worse than a blurred bush
VEHICLE_MIN_CONF = 0.35

_model = None
_lock = threading.Lock()


class DetectorMissing(Exception):
    pass


def _load():
    global _model
    with _lock:
        if _model is None:
            if not settings.DETECTOR_WEIGHTS.exists():
                raise DetectorMissing("models/yolo11n.pt is missing")
            from ultralytics import YOLO   # heavy import, only when first needed
            _model = YOLO(str(settings.DETECTOR_WEIGHTS))
    return _model


def detect(img: np.ndarray) -> list:
    """Returns [{"kind": "person"|"vehicle", "label", "box": [x0,y0,x1,y1] 0-1, "confidence"}]."""
    model = _load()
    h, w = img.shape[:2]
    res = model.predict(img, imgsz=960, conf=PERSON_MIN_CONF, verbose=False)[0]
    out = []
    for xyxy, cls, conf in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
        cls = int(cls)
        box = [xyxy[0] / w, xyxy[1] / h, xyxy[2] / w, xyxy[3] / h]
        if cls == PERSON_ID:
            out.append({"kind": "person", "label": "person", "box": box, "confidence": float(conf)})
        elif cls in VEHICLE_IDS and conf >= VEHICLE_MIN_CONF:
            out.append({"kind": "vehicle", "label": VEHICLE_IDS[cls], "box": box,
                        "confidence": float(conf)})
    return out


def blur_people(img: np.ndarray, people: list) -> np.ndarray:
    """Strong blur over every person box (slightly enlarged)."""
    out = img.copy()
    h, w = img.shape[:2]
    for p in people:
        x0, y0, x1, y1 = p["box"]
        mx, my = (x1 - x0) * 0.1, (y1 - y0) * 0.1
        a, b = max(0, int((x0 - mx) * w)), max(0, int((y0 - my) * h))
        c, d = min(w, int((x1 + mx) * w)), min(h, int((y1 + my) * h))
        if c - a < 2 or d - b < 2:
            continue
        region = out[b:d, a:c]
        small = cv2.resize(region, (max(1, (c - a) // 16), max(1, (d - b) // 16)),
                           interpolation=cv2.INTER_AREA)
        out[b:d, a:c] = cv2.GaussianBlur(
            cv2.resize(small, (c - a, d - b), interpolation=cv2.INTER_LINEAR), (0, 0), 6)
    return out

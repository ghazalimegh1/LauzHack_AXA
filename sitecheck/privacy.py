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
# Tuned on the key frames of our 3 test videos (2026-11-22): at 960 px (the size our frames
# already have) the detector found 11 sure vehicles instead of 6 and stopped calling a
# cargo bike a motorcycle and e-scooters people; ~55 ms per frame on a laptop CPU.
IMG_SIZE = 960
NMS_IOU = 0.5     # one box per object; class-agnostic, so a car is not also boxed as a truck
PEOPLE_IMG_SIZE = 640   # second, people-only look: a person either look finds is blurred

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


def _class_ids(model, names: set) -> list:
    """Detector class numbers for the names we use; everything else is never even reported."""
    return [i for i, n in model.names.items() if n in names]


def _boxes(result, w: int, h: int) -> list:
    out = []
    for cls, conf, box in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist(),
                              result.boxes.xyxy.tolist()):
        name = result.names[int(cls)]
        x0, y0, x1, y1 = box
        out.append({"kind": CLASS_MAP[name], "label": name,
                    "box": [x0 / w, y0 / h, x1 / w, y1 / h], "confidence": round(float(conf), 2)})
    return out


def _overlaps(a: list, b: list, limit: float = 0.5) -> bool:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return union > 0 and inter / union >= limit


def add_people(found: list, extra_people: list) -> list:
    """Privacy first: people from the second look that the first missed are added too."""
    people = [d for d in found if d["kind"] == "person"]
    new = [p for p in extra_people if not any(_overlaps(p["box"], q["box"]) for q in people)]
    return found + new


def detect(img: np.ndarray) -> list:
    """Boxes as fractions of width/height [x0, y0, x1, y1], so they fit any image size.
    Returns [{"kind": "vehicle"|"person", "label", "box", "confidence"}]."""
    model = _load()
    pil = _pil(img)
    w, h = pil.size
    main = model(pil, verbose=False, conf=MIN_CONF, iou=NMS_IOU, imgsz=IMG_SIZE,
                 classes=_class_ids(model, set(CLASS_MAP)), agnostic_nms=True)[0]
    people = model(pil, verbose=False, conf=MIN_CONF, imgsz=PEOPLE_IMG_SIZE,
                   classes=_class_ids(model, {"person"}))[0]
    return add_people(_boxes(main, w, h), _boxes(people, w, h))


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

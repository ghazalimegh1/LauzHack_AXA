"""Free, local object detection (YOLO11n, 5 MB, runs on a laptop CPU in ~0.1 s per frame).
It only knows everyday objects (cars, trucks, people...), not skylights or light wells,
so it handles what it can and the paid model is asked only about the rest.
It also finds people, who are blurred here before any frame leaves the computer.
If the package is not installed, the app still works: the paid model does it all.
"""
from __future__ import annotations

from PIL import Image, ImageFilter

from . import config

# Detector class -> our catalogue type. Everything else it sees is ignored.
CLASS_MAP = {"car": "vehicle", "truck": "vehicle", "bus": "vehicle",
             "motorcycle": "vehicle", "person": "person"}
HANDLES = {"vehicle"}   # types the paid model no longer needs to look for
MIN_CONF = 0.35   # shown from here...
SURE = 0.5        # ...counted in the score from here

_model = None


def available() -> bool:
    try:
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        return False


def _load():
    global _model
    if _model is None:  # load once; later frames reuse it
        from ultralytics import YOLO
        config.DETECTOR.parent.mkdir(exist_ok=True)
        _model = YOLO(str(config.DETECTOR))   # downloads the 5 MB file the first time
    return _model


def detect(img: Image.Image) -> list[dict]:
    """Boxes as fractions of width/height (x0, y0, x1, y1), so they fit any image size."""
    r = _load()(img, verbose=False, conf=MIN_CONF)[0]
    w, h = img.size
    out = []
    for cls, conf, box in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
        kind = CLASS_MAP.get(r.names[int(cls)])
        if kind:
            x0, y0, x1, y1 = box
            out.append({"kind": kind, "box": (x0 / w, y0 / h, x1 / w, y1 / h),
                        "conf": round(conf, 2), "by": "local detector (free)"})
    return out


def vehicle_seen(thumb: Image.Image) -> float:
    """How sure the detector is that this small frame shows a vehicle (0 = none).
    Used to pick key frames: ~30 ms per thumbnail, so even 120 sampled frames cost a few
    seconds and no money."""
    return max((o["conf"] for o in detect(thumb) if o["kind"] == "vehicle"), default=0.0)


def blur_people(img: Image.Image, objects: list[dict]) -> Image.Image:
    img = img.copy()
    w, h = img.size
    for o in objects:
        if o["kind"] == "person":
            x0, y0, x1, y1 = (int(o["box"][0] * w), int(o["box"][1] * h),
                              int(o["box"][2] * w), int(o["box"][3] * h))
            region = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(18))
            img.paste(region, (x0, y0))
    return img

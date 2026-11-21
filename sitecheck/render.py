"""Pictures for the website: key frames with coloured boxes, and crops of single objects."""
from __future__ import annotations

import cv2
import numpy as np

from . import settings


def _bgr(hex_colour: str) -> tuple:
    h = hex_colour.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)


def colour_for(f: dict) -> tuple:
    key = "uncertain" if f.get("uncertain") else f.get("label", "low")
    return _bgr(settings.RISK_COLOURS.get(key, "#5F5F5F"))


def encode(img: np.ndarray, quality: int = 85) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def with_boxes(img: np.ndarray, findings: list) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    thick = max(2, round(max(h, w) / 320))
    for f in findings:
        x0, y0, x1, y1 = f["box"]
        p0, p1 = (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h))
        c = colour_for(f)
        cv2.rectangle(out, p0, p1, c, thick, cv2.LINE_AA)
        tag = str(f["id"] + 1)
        scale = max(0.5, max(h, w) / 1400)
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        ty = max(th + 8, p0[1])
        cv2.rectangle(out, (p0[0], ty - th - 8), (p0[0] + tw + 10, ty), c, -1)
        cv2.putText(out, tag, (p0[0] + 5, ty - 5), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (255, 255, 255), 2, cv2.LINE_AA)
    return out


def crop(img: np.ndarray, box: list, min_side: int = 220) -> np.ndarray:
    """The object with some room around it, never smaller than min_side pixels."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2 * w, (y0 + y1) / 2 * h
    bw, bh = (x1 - x0) * w * 1.5, (y1 - y0) * h * 1.5
    side_w, side_h = max(bw, min_side), max(bh, min_side)
    a, b = int(max(0, cx - side_w / 2)), int(max(0, cy - side_h / 2))
    c, d = int(min(w, cx + side_w / 2)), int(min(h, cy + side_h / 2))
    return img[b:d, a:c]

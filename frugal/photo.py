"""Free checks on the photo before any AI sees it.
A dark or blurry photo would waste a paid call, so we ask for a retake instead."""
from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image, ImageOps

DIM = 70            # mean brightness (0-255) below which a frame is brightened
TARGET = 110        # ...towards this mean


def load(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    return ImageOps.exif_transpose(img).convert("RGB")  # phones store rotation in EXIF


def digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def problems(img: Image.Image) -> list[str]:
    found = []
    if min(img.size) < 400:
        found.append("Photo is very small; take it closer or at higher resolution.")
    mean, sharp = measure(img)
    if mean < 40:
        found.append("Photo is too dark.")
    elif mean > 235:
        found.append("Photo is overexposed.")
    if sharp < 30:
        found.append("Photo looks blurry.")
    return found


def measure(img: Image.Image) -> tuple[float, float]:
    """Brightness (0-255) and sharpness of an image, measured at a fixed size so
    photos and video frames are comparable."""
    gray = np.asarray(ImageOps.grayscale(_fit(img, 512)), dtype=np.float32)
    # Sharpness: edges give a high Laplacian variance, blur gives a low one.
    lap = (4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1]
           - gray[1:-1, :-2] - gray[1:-1, 2:])
    return float(gray.mean()), float(lap.var())


def walk_sharpness(img: Image.Image) -> float:
    """Sharpness for video frames, made for walking and night shots.
    1 Lamps are clipped first: a street light gives strong edges in a blurred frame.
    2 Edges are measured left-right and up-down separately, and the weaker one counts.
      Walking smears the picture in one direction; that direction loses its edges.
    3 If one direction is much weaker than the other (below 60%), the frame loses points
      in proportion: a smear with bright streaks can still have a strong "other" side.
    Night video (2026-11-21): the six visibly smeared frames all scored low here, while
    the Laplacian rated three of them among the sharpest of the video."""
    gray = np.asarray(ImageOps.grayscale(_fit(img, 512)), dtype=np.float32)
    gray = np.minimum(gray, np.percentile(gray, 97))
    across = np.abs(np.diff(gray, axis=1)).mean()
    down = np.abs(np.diff(gray, axis=0)).mean()
    weak, strong = sorted((across, down))
    return float(weak * min(1.0, weak / max(strong, 1e-6) / 0.6))


def _fit(img: Image.Image, max_px: int) -> Image.Image:
    img = img.copy()
    img.thumbnail((max_px, max_px))
    return img


def jpeg(img: Image.Image, max_px: int, quality: int = 70) -> bytes:
    # Image tokens grow with pixels, so the size we send is a direct cost lever.
    buf = io.BytesIO()
    _fit(img, max_px).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def brighten(img: Image.Image, mean: float) -> Image.Image:
    """Lifts the shadows of a dim frame (gamma curve), so the detector, the AI and the
    customer see more at night. Bright parts stay almost unchanged, so street lights do
    not burn out. Free: one lookup table per frame."""
    if mean >= DIM or mean <= 1:
        return img
    g = min(1.0, max(0.4, np.log(TARGET / 255) / np.log(mean / 255)))
    lut = [round(255 * (i / 255) ** g) for i in range(256)]
    return img.point(lut * 3)

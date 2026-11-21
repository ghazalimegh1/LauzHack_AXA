"""Free checks on the photo before any AI sees it.
A dark or blurry photo would waste a paid call, so we ask for a retake instead."""
from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image, ImageOps


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


def _fit(img: Image.Image, max_px: int) -> Image.Image:
    img = img.copy()
    img.thumbnail((max_px, max_px))
    return img


def jpeg(img: Image.Image, max_px: int, quality: int = 70) -> bytes:
    # Image tokens grow with pixels, so the size we send is a direct cost lever.
    buf = io.BytesIO()
    _fit(img, max_px).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()

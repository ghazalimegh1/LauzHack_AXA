"""Video -> a handful of sharp, different key frames. Free code, no AI.

1. Decode the video once and keep 2 frames per second, by real timestamp.
2. Measure every kept frame: brightness, overexposure, sharpness and walking blur.
   Bright lamps are masked out first, so a street lamp does not make a frame look sharp.
3. Drop dark, overexposed and blurry frames, judged against THIS video's own median,
   so a night video is compared with itself, not with daylight.
4. Split the walk into equal parts and take the sharpest frame of each part, skipping
   views that were already picked. Sharpness alone decides.
5. Brighten dim key frames so the AI (and the customer) can see them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from . import settings

MEASURE_W = 320            # frames are measured at this width (fast, and enough)
THUMB_H = 120              # filmstrip thumbnails
LAMP_LEVEL = 235           # pixels this bright (and their surroundings) are ignored
SAME_VIEW = 0.80           # tiny-thumbnail correlation above this = same view (measured:
                           # same spot 0.87; 99% of frames 3+ s apart stay below 0.64)


@dataclass
class Sample:
    index: int
    t: float
    jpeg: bytes                      # frame at WORK_PX, kept compressed in memory
    thumb: bytes                     # small JPEG for the filmstrip
    brightness: float = 0.0
    overexposed: float = 0.0
    sharpness: float = 0.0
    streak: float = 1.0              # 1 = even detail in all directions, low = smeared
    tiny: np.ndarray = field(default=None, repr=False)
    status: str = "skipped"
    reason: str = ""

    def public(self) -> dict:
        return {"index": self.index, "t": round(self.t, 2), "status": self.status,
                "reason": self.reason, "sharpness": round(self.sharpness, 1),
                "brightness": round(self.brightness, 1)}


def _fit(img: np.ndarray, longest: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = longest / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def measure(gray: np.ndarray) -> dict:
    """Quality numbers for one grey frame (any size; resized to MEASURE_W wide)."""
    h, w = gray.shape[:2]
    if w != MEASURE_W:
        gray = cv2.resize(gray, (MEASURE_W, max(1, round(h * MEASURE_W / w))),
                          interpolation=cv2.INTER_AREA)
    lamps = (gray >= LAMP_LEVEL).astype(np.uint8)
    lamps = cv2.dilate(lamps, np.ones((9, 9), np.uint8)) > 0
    keep = ~lamps
    if keep.mean() < 0.2:          # almost all bright: nothing sensible to mask
        keep = np.ones_like(keep)
    g = gray.astype(np.float32)
    lap = cv2.Laplacian(g, cv2.CV_32F)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    ex, ey = float((gx[keep] ** 2).mean()), float((gy[keep] ** 2).mean())
    tiny = cv2.resize(gray, (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    return {
        "brightness": float(gray.mean()),
        "overexposed": float((gray >= 250).mean()),
        "sharpness": float(lap[keep].var()),
        "streak": min(ex, ey) / max(ex, ey) if max(ex, ey) > 0 else 1.0,
        "tiny": tiny - tiny.mean(),
    }


def read_samples(path: str) -> tuple:
    """Decodes the video once. Returns (samples, info)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("This file could not be opened as a video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = count / fps if fps else 0
    step = max(1.0 / settings.SAMPLES_PER_S, duration / settings.MAX_SAMPLES if duration else 0)
    samples, next_t, frames_seen, size = [], 0.0, 0, None
    while cap.grab():
        frames_seen += 1
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if t + 1e-3 < next_t:
            continue
        ok, frame = cap.retrieve()
        if not ok or frame is None:
            continue
        size = size or (frame.shape[1], frame.shape[0])
        while next_t <= t + 1e-3:
            next_t += step
        work = _fit(frame, settings.WORK_PX)
        gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        th = THUMB_H / work.shape[0]
        thumb = cv2.resize(work, (round(work.shape[1] * th), THUMB_H), interpolation=cv2.INTER_AREA)
        s = Sample(index=len(samples), t=t,
                   jpeg=cv2.imencode(".jpg", work, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes(),
                   thumb=cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes())
        m = measure(gray)
        s.tiny = m.pop("tiny")
        for k, v in m.items():
            setattr(s, k, v)
        samples.append(s)
    cap.release()
    if not samples:
        raise ValueError("No frames could be read from this video.")
    duration = max(duration, samples[-1].t)
    info = {"duration_s": round(duration, 2), "fps": round(fps, 2), "frames_in_video": frames_seen,
            "width": size[0] if size else 0, "height": size[1] if size else 0}
    return samples, info


def _same_view(a: Sample, b: Sample) -> bool:
    na, nb = np.linalg.norm(a.tiny), np.linalg.norm(b.tiny)
    if na < 1e-6 or nb < 1e-6:
        return False
    return float(a.tiny @ b.tiny / (na * nb)) > SAME_VIEW


def judge(samples: list) -> None:
    """Marks dark / overexposed / blurry frames, relative to this video's medians."""
    med_b = float(np.median([s.brightness for s in samples]))
    med_o = float(np.median([s.overexposed for s in samples]))
    med_s = float(np.median([s.sharpness for s in samples]))
    med_k = float(np.median([s.streak for s in samples]))
    for s in samples:
        if s.brightness < max(12.0, 0.5 * med_b):
            s.reason = "too dark"
        elif s.overexposed > max(0.30, 3 * med_o):
            s.reason = "overexposed"
        elif s.sharpness < 0.45 * med_s:
            s.reason = "blurry"
        elif s.streak < 0.5 * med_k:
            s.reason = "blurred by walking"
        else:
            s.reason = ""
            s.status = "usable"


def pick(samples: list, k: int) -> list:
    """Equal parts of the walk, sharpest usable frame of each, no repeated views."""
    judge(samples)
    t0, t1 = samples[0].t, samples[-1].t
    span = max(t1 - t0, 1e-6)
    parts = [[] for _ in range(k)]
    for s in samples:
        parts[min(k - 1, int((s.t - t0) / span * k))].append(s)
    picked = []

    def try_take(candidates) -> bool:
        for s in sorted(candidates, key=lambda x: -x.sharpness):
            if s.status != "usable":
                continue
            if any(_same_view(s, p) for p in picked):
                s.reason = "same view as a picked frame"
                continue
            s.status, s.reason = "picked", ""
            picked.append(s)
            return True
        return False

    for part in parts:
        try_take(part)
    if len(picked) < k:                       # an empty part: use the best leftovers
        try_take_all = [s for s in samples if s.status == "usable"]
        while len(picked) < k and try_take(try_take_all):
            pass
    if not picked:                            # nothing usable at all: still give one frame
        best = max(samples, key=lambda x: x.sharpness)
        best.status, best.reason = "picked", ""
        picked.append(best)
    for s in samples:
        if s.status == "usable":
            s.status, s.reason = "skipped", s.reason or "a sharper frame was picked nearby"
        elif s.status != "picked":
            s.status = "skipped"
    return sorted(picked, key=lambda x: x.t)


def brighten(img: np.ndarray) -> tuple:
    """Lifts dim frames: local contrast (CLAHE) on lightness, then a gentle gamma."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    light = lab[:, :, 0]
    mean = float(light.mean())
    if mean >= 100:
        return img, False
    light = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(light)
    m = max(float(light.mean()), 1.0) / 255.0
    gamma = float(np.clip(np.log(0.45) / np.log(m), 0.4, 1.0))
    lut = (np.clip(((np.arange(256) / 255.0) ** gamma) * 255.0, 0, 255)).astype(np.uint8)
    lab[:, :, 0] = cv2.LUT(light, lut)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), True


def decode(jpeg: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)

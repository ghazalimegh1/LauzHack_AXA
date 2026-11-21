"""Video -> a handful of sharp, different key frames. Free code, no AI.

The choosing rules are the team's earlier frame picker (frugal/video.py and photo.py),
ported unchanged, because it found the goods and machines that a newer picker missed:
1. Decode the video once and keep 2 frames per second, by real timestamp.
2. Measure a 480 px copy of every kept frame: brightness, and "walking sharpness":
   bright lamps are clipped, edges are measured left-right and up-down, and the weaker
   direction counts (walking smears the picture in one direction).
3. Drop dark, overexposed and blurry frames, judged against THIS video's own median,
   so a night video is compared with itself, not with daylight.
4. Split the walk into equal parts and take the best frame of each part (sharpness
   against the video's median, capped at 2x), unless a 32x18 grey miniature shows it is
   the same view as a frame already picked. Sharpness alone decides.
5. Brighten dim key frames (gamma curve) so the AI and the customer can see them.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from . import settings

MEASURE_PX = 480           # frames are measured at this size (the earlier app's thumbnail)
THUMB_H = 160              # filmstrip thumbnails
DUP_DIFF = 10              # mean grey difference (0-255) of the miniatures: below = same view
DARK_ABS, DARK_REL = 40, 0.45   # dark = below 40, or below 45% of the median if that is lower
DARK_MIN = 12              # ...but always dark below this: nothing to see at all
BLUR_MIN = 0.5             # walking sharpness below which a frame is always blurry
DIM, TARGET = 70, 110      # frames darker than DIM are brightened towards TARGET


@dataclass
class Sample:
    index: int
    t: float
    jpeg: bytes                      # frame at WORK_PX, kept compressed in memory
    thumb: bytes                     # small JPEG for the filmstrip
    brightness: float = 0.0
    sharpness: float = 0.0           # walking sharpness (see measure)
    tiny: np.ndarray = field(default=None, repr=False)   # 32x18 grey miniature
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
    """Brightness, walking sharpness and a miniature for one grey frame (any size)."""
    gray = _fit(gray, MEASURE_PX).astype(np.float32)
    clipped = np.minimum(gray, np.percentile(gray, 97))      # street lamps do not count
    across = float(np.abs(np.diff(clipped, axis=1)).mean())
    down = float(np.abs(np.diff(clipped, axis=0)).mean())
    weak, strong = sorted((across, down))
    return {
        "brightness": float(gray.mean()),
        # a smear in one direction loses points in proportion, below 60% of the other side
        "sharpness": weak * min(1.0, weak / max(strong, 1e-6) / 0.6),
        # 32x18 grey miniature, made as in the earlier app (PIL resize): ignores small shake
        "tiny": np.asarray(Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8)).resize((32, 18)),
                           dtype=np.float32),
    }


def _backends() -> list:
    # Hardware decode on macOS is ~3x faster for 4K HEVC phone videos (earlier app, M2:
    # ~10 s instead of 29 s). Both backends turn portrait videos upright.
    if sys.platform == "darwin":
        return [cv2.CAP_AVFOUNDATION, cv2.CAP_FFMPEG]
    return [cv2.CAP_FFMPEG]


def _fps(cap) -> float:
    fps = cap.get(cv2.CAP_PROP_FPS)
    # Some files report 0, NaN or nonsense like 90000 (a time base, not a frame rate).
    return fps if fps and math.isfinite(fps) and 1 <= fps <= 240 else 30.0


def _timestamp(cap, idx: int, fps: float, prev: float) -> float:
    """Seconds of the frame just grabbed: the file's own timestamp (right for variable
    frame rate), or counted frames if the backend does not report one."""
    t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
    if idx == 0 or t > prev:
        return t
    return max(idx / fps, prev + 1e-6)


def _measure_copy(frame: np.ndarray) -> np.ndarray:
    """The grey 480 px copy the earlier app measured: 1280 px with OpenCV, then a PIL
    thumbnail and PIL's grey conversion (the numbers depend a little on this path)."""
    img = Image.fromarray(cv2.cvtColor(_fit(frame, 1280), cv2.COLOR_BGR2RGB))
    img.thumbnail((MEASURE_PX, MEASURE_PX))
    return np.asarray(img.convert("L"))


def _sample_with(path: str, backend: int) -> tuple:
    cap = cv2.VideoCapture(str(path), backend)
    if not cap.isOpened():
        return [], {}
    fps = _fps(cap)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    # The header's frame count is only a hint; the thinning below is the real bound.
    every = max(1.0 / settings.SAMPLES_PER_S, count / fps / settings.MAX_SAMPLES)
    samples, idx, t, next_t, size = [], 0, 0.0, 0.0, None
    while cap.grab():                       # grab() decodes but does not convert the image
        t = _timestamp(cap, idx, fps, t)
        idx += 1
        if t + 0.5 / fps < next_t:          # half a frame of tolerance for rounded timestamps
            continue
        ok, frame = cap.retrieve()
        if not ok or frame is None:
            continue
        size = size or (frame.shape[1], frame.shape[0])
        next_t = t + every
        work = _fit(frame, settings.WORK_PX)
        th = THUMB_H / work.shape[0]
        thumb = cv2.resize(work, (round(work.shape[1] * th), THUMB_H), interpolation=cv2.INTER_AREA)
        s = Sample(index=len(samples), t=t,
                   jpeg=cv2.imencode(".jpg", work, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes(),
                   thumb=cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes())
        m = measure(_measure_copy(frame))
        s.tiny = m.pop("tiny")
        for k, v in m.items():
            setattr(s, k, v)
        samples.append(s)
        if len(samples) > settings.MAX_SAMPLES:
            # Longer than the header said: keep every second sample, step twice as wide.
            samples, every = samples[::2], every * 2
            for i, kept in enumerate(samples):
                kept.index = i
            next_t = samples[-1].t + every
    cap.release()
    info = {"duration_s": round(t + 1 / fps if idx else 0.0, 2), "fps": round(fps, 2),
            "frames_in_video": idx, "width": size[0] if size else 0,
            "height": size[1] if size else 0}
    return samples, info


def read_samples(path: str) -> tuple:
    """Decodes the video once. Returns (samples, info)."""
    for backend in _backends():
        samples, info = _sample_with(path, backend)
        if samples:
            return samples, info
    raise ValueError("This file could not be read as a video (try MP4 or MOV).")


def _same_view(a: Sample, b: Sample) -> bool:
    return float(np.abs(a.tiny - b.tiny).mean()) < DUP_DIFF


def judge(samples: list) -> float:
    """Marks dark / overexposed / blurry frames, relative to this video's medians.
    Returns the median sharpness."""
    med_s = float(np.median([s.sharpness for s in samples]))
    blur_limit = max(BLUR_MIN, 0.5 * med_s)
    dark_limit = max(DARK_MIN, min(DARK_ABS, DARK_REL * float(np.median([s.brightness for s in samples]))))
    for s in samples:
        s.status = "skipped"
        if s.brightness < dark_limit:
            s.reason = "dark"
        elif s.brightness > 235:
            s.reason = "overexposed"
        elif s.sharpness < blur_limit:
            s.reason = "blurry"
        else:
            s.reason, s.status = "", "usable"
    return med_s


def pick(samples: list, k: int) -> list:
    """Equal parts of the walk, best usable frame of each, no repeated views."""
    med_s = judge(samples)

    def quality(s):         # capped: lamps and noise make some night frames look "sharp"
        return min(2.0, s.sharpness / max(med_s, 1e-6))

    picked = []

    def try_take(candidates) -> bool:
        # sorted() is stable, so ties keep the earlier frame
        for s in sorted((c for c in candidates if c.status == "usable"), key=quality, reverse=True):
            if any(_same_view(s, p) for p in picked):
                s.status, s.reason = "skipped", "same view"
                continue
            s.status, s.reason = "picked", ""
            picked.append(s)
            return True
        return False

    bounds = np.linspace(0, len(samples), k + 1).astype(int)
    for a, b in zip(bounds[:-1], bounds[1:]):
        try_take(samples[a:b])
    while len(picked) < k and try_take(samples):   # a part without a usable frame
        pass
    if not picked:                            # nothing usable at all: still give one frame
        best = max(samples, key=lambda x: x.sharpness)
        best.status, best.reason = "picked", ""
        picked.append(best)
    for s in samples:
        if s.status == "usable":
            s.status, s.reason = "skipped", "sharper nearby"
    return sorted(picked, key=lambda x: x.t)


def brighten(img: np.ndarray) -> tuple:
    """Lifts the shadows of a dim frame with a gamma curve; bright parts (street lights)
    stay almost unchanged. Returns (image, changed)."""
    mean = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())
    if mean >= DIM or mean <= 1:
        return img, False
    g = min(1.0, max(0.4, np.log(TARGET / 255) / np.log(mean / 255)))
    lut = np.array([round(255 * (i / 255) ** g) for i in range(256)], np.uint8)
    return cv2.LUT(img, lut), True


def decode(jpeg: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)

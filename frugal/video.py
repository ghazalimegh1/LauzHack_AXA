"""Video -> a handful of key frames, for free (no AI involved).

A 60 s phone video has ~1,800 frames. Neighbouring frames are nearly identical,
many are blurred by walking, so paying a model to look at all of them is waste.
Steps, each cheaper than any model call:
  1 decode once, keep 2 frames per second (by real timestamp, so variable frame rate works)
  2 drop dark, overexposed and motion-blurred     (brightness + edge sharpness)
  3 split the walk into equal parts, take the sharpest frame of each part
    unless it shows the same view as a frame already picked
  4 the picked frames come from a compact copy kept during step 1 (no second decode)
Every sampled frame keeps a reason, so the demo can show what was picked and why.

Phone videos (measured on an Apple M2, iPhone clip: HEVC, 3840x2160, 60 fps, 47 s, 302 MB):
  FFmpeg backend (software decode):        28.9 s to sample, 37.3 s end to end
  AVFoundation backend (hardware decode):  ~10 s to decode every frame
So on macOS we try AVFoundation first and fall back to FFmpeg. Both apply the
phone's rotation tag the same way (checked with a portrait-tagged clip), so
portrait videos come out upright.
"""
from __future__ import annotations

import io
import math
import os
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from . import config, photo

THUMB_PX = 480      # enough to judge sharpness and to draw the filmstrip
KEEP_PX = 1280      # picked frames: detail for the detector and the screen
KEEP_JPEG_Q = 90    # sampled frames are kept as JPEG: ~150 KB instead of 2.7 MB raw
DUP_DIFF = 10       # mean pixel difference (0-255) below which two views count as the same
FALLBACK_FPS = 30.0


# ---------------- decoding ----------------
def _backends() -> list[int]:
    # Hardware decode on macOS is ~3x faster for 4K HEVC (see the numbers above).
    if sys.platform == "darwin":
        return [cv2.CAP_AVFOUNDATION, cv2.CAP_FFMPEG]
    return [cv2.CAP_FFMPEG]


def _fps(cap) -> float:
    fps = cap.get(cv2.CAP_PROP_FPS)
    # Some files report 0, NaN or nonsense like 90000 (a time base, not a frame rate).
    return fps if fps and math.isfinite(fps) and 1 <= fps <= 240 else FALLBACK_FPS


def _timestamp(cap, idx: int, fps: float, prev: float) -> float:
    """Seconds of the frame just grabbed. The container's own timestamp is right
    for variable frame rate; if a backend does not report it, count frames."""
    t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
    if idx == 0 or t > prev:
        return t
    return max(idx / fps, prev + 1e-6)


def _resize(bgr: np.ndarray, max_px: int) -> np.ndarray:
    # OpenCV shrinks a 4K array several times faster than PIL does.
    h, w = bgr.shape[:2]
    scale = max_px / max(h, w)
    if scale >= 1:
        return bgr
    return cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def _keep(bgr: np.ndarray, idx: int, t: float) -> dict:
    img = Image.fromarray(cv2.cvtColor(_resize(bgr, KEEP_PX), cv2.COLOR_BGR2RGB))
    thumb = img.copy()
    thumb.thumbnail((THUMB_PX, THUMB_PX))
    buf = io.BytesIO()
    # Keeping a compact copy now is cheaper than seeking back later:
    # one seek in a 4K HEVC file took ~0.6 s with FFmpeg, one JPEG encode ~10 ms.
    img.save(buf, format="JPEG", quality=KEEP_JPEG_Q)
    return {"idx": idx, "t": t, "thumb": thumb, "_jpeg": buf.getvalue()}


def _sample_with(path: str, backend: int) -> dict:
    cap = cv2.VideoCapture(path, backend)
    if not cap.isOpened():
        return {"frames": []}
    fps = _fps(cap)
    meta_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    # The frame count from the file header is only a hint (it can be 0 or wrong),
    # so it only sets the first sampling step; the thinning below is the real bound.
    every = max(config.SAMPLE_EVERY_S, meta_count / fps / config.MAX_SAMPLES)

    frames, idx, t, next_t = [], 0, 0.0, 0.0
    while cap.grab():                     # grab() decodes but does not convert the image
        t = _timestamp(cap, idx, fps, t)
        if t + 0.5 / fps >= next_t:       # half a frame of tolerance for rounded timestamps
            ok, bgr = cap.retrieve()
            if ok and bgr is not None:
                frames.append(_keep(bgr, idx, t))
                next_t = t + every
                if len(frames) > config.MAX_SAMPLES:
                    # Longer than the header said: keep every second sample, step twice as wide.
                    frames, every = frames[::2], every * 2
                    next_t = frames[-1]["t"] + every
        idx += 1
    cap.release()
    return {"fps": fps, "total": idx, "duration": t + 1 / fps if idx else 0.0,
            "frames": frames}


def _sample(path: str) -> dict:
    for backend in _backends():
        info = _sample_with(path, backend)
        if info["frames"]:
            return info
    raise ValueError("Could not read this video (try MP4 or MOV).")


# ---------------- choosing ----------------
def _signature(img: Image.Image) -> np.ndarray:
    # A 32x18 grey miniature: cheap to compare, ignores small camera shake.
    return np.asarray(img.convert("L").resize((32, 18)), dtype=np.float32)


def _choose(frames: list[dict], k: int) -> None:
    """Marks frames in place: picked (with number n) or a reason why not."""
    for f in frames:
        f["mean"], f["sharp"] = photo.measure(f["thumb"])
        f["sig"] = _signature(f["thumb"])
        f["picked"], f["n"], f["reason"] = False, None, ""
    if not frames:
        return
    # Blur is judged relative to this video: a dim hall is never as crisp as a sunny yard.
    blur_limit = max(30.0, 0.4 * float(np.median([f["sharp"] for f in frames])))
    for f in frames:
        if f["mean"] < 40:
            f["reason"] = "dark"
        elif f["mean"] > 235:
            f["reason"] = "overexposed"
        elif f["sharp"] < blur_limit:
            f["reason"] = "blurry"

    picked: list[dict] = []
    bounds = np.linspace(0, len(frames), k + 1).astype(int)
    for a, b in zip(bounds[:-1], bounds[1:]):
        part = sorted((f for f in frames[a:b] if not f["reason"]),
                      key=lambda f: f["sharp"], reverse=True)
        for f in part:
            same = next((p for p in picked
                         if np.abs(f["sig"] - p["sig"]).mean() < DUP_DIFF), None)
            if same is None:
                f["picked"] = True
                picked.append(f)
                break
            f["reason"] = "same view"
    for i, f in enumerate(sorted(picked, key=lambda f: f["t"]), start=1):
        f["n"] = i                        # #1, #2, ... in walking order
    for f in frames:
        if not f["picked"] and not f["reason"]:
            f["reason"] = "sharper nearby"


def _unpack(frames: list[dict]) -> None:
    """Picked frames get their full-size image back; the rest drop their copy to free memory."""
    for f in frames:
        data = f.pop("_jpeg", None)
        if f["picked"] and data:
            f["img"] = Image.open(io.BytesIO(data)).convert("RGB")


# ---------------- public ----------------
def keyframes_from_path(path: str, k: int | None = None) -> dict:
    """Returns all sampled frames (with picked / reason) and the picked ones."""
    info = _sample(path)
    _choose(info["frames"], k or config.KEYFRAMES)
    _unpack(info["frames"])
    info["picked"] = sorted((f for f in info["frames"] if f["picked"]), key=lambda f: f["n"])
    return info


def keyframes(video_bytes: bytes, k: int | None = None, suffix: str = ".mp4") -> dict:
    # OpenCV reads from a file path, not from memory. iPhones name files IMG_1234.MOV:
    # normalise the suffix ("MOV", ".MOV", "" -> ".mov" / ".mp4") so the container is recognised.
    suffix = "." + (suffix or ".mp4").lstrip(".").lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(video_bytes)
        path = tmp.name
    try:
        return keyframes_from_path(path, k)
    finally:
        os.unlink(path)


def filmstrip(frames: list[dict], cols: int = 12, w: int = 128) -> Image.Image:
    """One overview image: every sampled frame, picked ones framed in green.
    Portrait videos get tall, narrow tiles and more of them per row."""
    portrait = bool(frames) and frames[0]["thumb"].height > frames[0]["thumb"].width
    if portrait:
        w, cols = w * 9 // 16, cols * 16 // 9
    h = int(w * 16 / 9) if portrait else int(w * 9 / 16)
    label_h = 38 if portrait else 24      # narrow tiles need the label on two lines
    rows = max(1, -(-len(frames) // cols))
    sheet = Image.new("RGB", (cols * (w + 6) + 6, rows * (h + label_h) + 6), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=12)
    for i, f in enumerate(frames):
        x, y = 6 + (i % cols) * (w + 6), 6 + (i // cols) * (h + label_h)
        tile = f["thumb"].copy()
        tile.thumbnail((w, h))
        if not f["picked"]:
            tile = ImageEnhance.Brightness(tile.convert("L").convert("RGB")).enhance(0.55)
        sheet.paste(tile, (x + (w - tile.width) // 2, y + (h - tile.height) // 2))
        sep = "\n" if portrait else " "
        if f["picked"]:
            draw.rectangle([x - 3, y - 3, x + w + 2, y + h + 2], outline="#1b9e4b", width=4)
            label, colour = f"#{f['n']}{sep}{f['t']:.1f}s", "#1b9e4b"
        else:
            label, colour = f"{f['t']:.1f}s{sep}{f['reason']}", "#888888"
        draw.text((x, y + h + 5), label, fill=colour, font=font)
    return sheet

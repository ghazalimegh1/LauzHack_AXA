"""Pictures for the website: key frames with labelled boxes, crops of single objects, and
the frames overview (filmstrip). The filmstrip layout is ported from the team's earlier
frugal/video.py; boxes carry their number, name and risk label like the earlier app."""
from __future__ import annotations

import io
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from . import frames, settings

PRIVACY = "#3B3FD8"
GREEN = "#1b9e4b"
FONTS = ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


@lru_cache(maxsize=8)
def font(size: int):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def colour_for(f: dict) -> str:
    return settings.RISK_COLOURS.get(f.get("label", ""), "#8A8A8A")


def encode(img: np.ndarray, quality: int = 85) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def _to_pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(img[:, :, ::-1].copy())


def _label_box(draw, xy, text, colour, size, img_w):
    """A filled tag with white text, sitting on top of the box (inside it if no room)."""
    f = font(size)
    x0, y0 = xy
    tw = draw.textlength(text, font=f)
    pad = max(3, size // 4)
    h = size + 2 * pad
    top = y0 - h if y0 - h >= 0 else y0
    x0 = max(0, min(x0, img_w - tw - 2 * pad))
    draw.rectangle([x0, top, x0 + tw + 2 * pad, top + h], fill=colour)
    draw.text((x0 + pad, top + pad - 1), text, fill="white", font=f)


def with_boxes(img: np.ndarray, findings: list, people: list = ()) -> np.ndarray:
    pil = _to_pil(img)
    draw = ImageDraw.Draw(pil)
    w, h = pil.size
    thick = max(2, round(max(w, h) / 360))
    size = max(13, round(max(w, h) / 48))
    for p in people:
        x0, y0, x1, y1 = p["box"]
        draw.rectangle([x0 * w, y0 * h, x1 * w, y1 * h], outline=PRIVACY, width=thick)
        _label_box(draw, (x0 * w, y0 * h), "person", PRIVACY, size, w)
    for f in findings:
        x0, y0, x1, y1 = f["box"]
        c = colour_for(f)
        draw.rectangle([x0 * w, y0 * h, x1 * w, y1 * h], outline=c, width=thick)
        # the model's plain name ("pallets") when it gave one, else our category name
        tag = f"{f['id'] + 1} {(f.get('detail') or f['name']).lower()} | {f['label'].upper()}"
        _label_box(draw, (x0 * w, y0 * h), tag, c, size, w)
    return np.asarray(pil)[:, :, ::-1].copy()


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


# Measured on our test videos (2026-11-22): every close-up a person could recognise scored
# 3.3 or more, the two night "blinds" close-ups that showed only smeared paving 0.9 and 1.6.
PHOTO_MIN_SHARPNESS = 2.5
PHOTO_MIN_PX = 32       # a box smaller than this (in the 960 px key frame) shows no detail


def photo_ok(img: np.ndarray, box: list) -> bool:
    """Whether the close-up of this box is worth showing. Never changes the box itself."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    if min(x1 - x0, y1 - y0) < PHOTO_MIN_PX:
        return False
    gray = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return frames.measure(gray)["sharpness"] >= PHOTO_MIN_SHARPNESS


# --- Display-only clean-up -------------------------------------------------------------
# Only people see these pictures. The AI keeps getting the plain, small frames (cheap, and
# its answers were checked on those), so nothing below may run before an AI call.
DIM_FULL, DIM_NONE = 100, 140   # mean lightness (0-255): full clean-up below, none above
DISPLAY_PX = 640                # small crops are enlarged to this longest side
DISPLAY_QUALITY = 92            # few, small pictures: worth a high JPEG quality


def dimness(img: np.ndarray) -> float:
    """0 for a daylight picture, 1 for a night one, smoothly in between. Judged on the
    picture as stored, i.e. after the gamma lift in frames.brighten."""
    light = float(cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[:, :, 0].mean())
    return float(np.clip((DIM_NONE - light) / (DIM_NONE - DIM_FULL), 0.0, 1.0))


def _denoise(img: np.ndarray, strength: float) -> np.ndarray:
    # Night frames are grainy; the contrast and sharpening steps would enlarge the grain.
    # Only a light edge-keeping blur over a 5 px window: phones already smooth night video,
    # and stronger filters (non-local means) left flat blobs that the 3x enlargement
    # turned into a watercolour look. Leaves and paving keep their texture this way.
    return cv2.bilateralFilter(img, 5, 6 + 8 * strength, 3)


def _local_contrast(img: np.ndarray, strength: float) -> np.ndarray:
    """CLAHE on lightness only, so shadows show detail without the colours shifting,
    then a gentle lift of the mid-tones (bright lamps hardly change)."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    light = lab[:, :, 0]
    # ~128 px tiles whatever the size: smaller tiles turn flat walls and paving blotchy
    tiles = max(1, round(max(light.shape) / 128))
    clahe = cv2.createCLAHE(clipLimit=1.0 + 0.5 * strength, tileGridSize=(tiles, tiles))
    g = 1 - 0.2 * strength
    lift = np.array([round(255 * (i / 255) ** g) for i in range(256)], np.uint8)
    lab[:, :, 0] = cv2.LUT(clahe.apply(light), lift)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _enlarge(img: np.ndarray, longest: int) -> np.ndarray:
    """Lanczos keeps edges crisper than the browser's own stretching; never shrinks."""
    h, w = img.shape[:2]
    scale = longest / max(h, w)
    if scale <= 1:
        return img
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_LANCZOS4)


def _sharpen(img: np.ndarray, amount: float) -> np.ndarray:
    """Unsharp mask on lightness only: colour noise is not sharpened, and a small radius
    with a small amount gives no visible halos."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    light = lab[:, :, 0]
    blur = cv2.GaussianBlur(light, (0, 0), 1.2)
    lab[:, :, 0] = cv2.addWeighted(light, 1 + amount, blur, -amount, 0)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def for_display(img: np.ndarray, longest: int = 0, night: float = None) -> np.ndarray:
    """A clearer copy for people: night pictures are cleaned, lifted and sharpened;
    daylight ones only get a light sharpening. longest > 0 enlarges small pictures.
    night: the dimness to use (default: this picture's own)."""
    s = dimness(img) if night is None else night
    if s > 0:
        img = _local_contrast(_denoise(img, s), s)
    if longest:
        img = _enlarge(img, longest)
    return _sharpen(img, 0.2 + 0.3 * s)


def display_crop(img: np.ndarray, box: list) -> bytes:
    """The crop shown on the page: cleaned at its own size (cheaper, and the grain is still
    fine there), then enlarged, as a high-quality JPEG. Night or day is judged on the
    whole frame: a car under a street lamp is still a grainy night picture."""
    return encode(for_display(crop(img, box), DISPLAY_PX, dimness(img)), DISPLAY_QUALITY)


def filmstrip(samples: list, thumbs: list, cols: int = 12, w: int = 128) -> bytes:
    """One overview image: every sampled frame, picked ones framed in green with their
    number, skipped ones grey with the reason. Portrait videos get tall, narrow tiles and
    more of them per row. samples: the public sample dicts; thumbs: their JPEG bytes."""
    tiles = [Image.open(io.BytesIO(t)).convert("RGB") for t in thumbs]
    portrait = bool(tiles) and tiles[0].height > tiles[0].width
    if portrait:
        w, cols = w * 9 // 16, cols * 16 // 9
    h = int(w * 16 / 9) if portrait else int(w * 9 / 16)
    label_h = 38 if portrait else 24      # narrow tiles need the label on two lines
    rows = max(1, -(-len(tiles) // cols))
    sheet = Image.new("RGB", (cols * (w + 6) + 6, rows * (h + label_h) + 6), "white")
    draw = ImageDraw.Draw(sheet)
    f = font(12)
    order = {s["index"]: n for n, s in enumerate(
        sorted((s for s in samples if s["status"] == "picked"), key=lambda s: s["t"]), start=1)}
    for i, (s, tile) in enumerate(zip(samples, tiles)):
        x, y = 6 + (i % cols) * (w + 6), 6 + (i // cols) * (h + label_h)
        tile = tile.copy()
        tile.thumbnail((w, h))
        picked = s["status"] == "picked"
        if not picked:
            tile = ImageEnhance.Brightness(tile.convert("L").convert("RGB")).enhance(0.55)
        sheet.paste(tile, (x + (w - tile.width) // 2, y + (h - tile.height) // 2))
        sep = "\n" if portrait else " "
        if picked:
            draw.rectangle([x - 3, y - 3, x + w + 2, y + h + 2], outline=GREEN, width=4)
            label, colour = f"#{order[s['index']]}{sep}{s['t']:.1f}s", GREEN
        else:
            label, colour = f"{s['t']:.1f}s{sep}{s['reason']}", "#888888"
        draw.text((x, y + h + 5), label, fill=colour, font=f)
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=88)
    return buf.getvalue()

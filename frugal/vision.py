"""The only place that talks to a paid model.
Two backends with the same shape: the Claude API (if ANTHROPIC_API_KEY is set)
or OpenRouter. Answers are tiny JSON, so output tokens stay low.

  ask()  one photo, yes/no/unclear questions          (single-photo check)
  find() several video frames in ONE call, object list (site video check)
         One call instead of one per frame: the instructions are paid for once.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import time

import requests
from PIL import Image

from . import cache, config
from .objects import CATALOGUE

ANSWERS = {"y", "n", "u"}
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


# ---------------- transport ----------------
# 2026-11-21, during the hackathon: OpenRouter answered "429: google/gemini-2.5-flash-lite is
# temporarily rate-limited upstream" (Google's shared pool, not our key or credit). One try
# then lost every AI finding. So: a busy answer is retried after a short wait, and if the
# model stays busy, find() moves on to a similar model (config.FALLBACKS).
BUSY = {429, 500, 502, 503, 504}   # "try again" answers; 400/401/402 would fail again
WAITS = (2, 5)                     # seconds before the 2nd and 3rd try (~7 s at most)


def _post(url: str, **kwargs) -> requests.Response:
    for wait in (0, *WAITS):
        time.sleep(wait)
        try:
            r = requests.post(url, **kwargs)
        except (requests.Timeout, requests.ConnectionError):
            if wait == WAITS[-1]:
                raise
            continue
        if r.status_code not in BUSY or wait == WAITS[-1]:
            break
    r.raise_for_status()
    return r


def _usd(model: str, tok_in: int, tok_out: int, reported=None) -> float | None:
    if reported is not None:
        return float(reported)          # OpenRouter's own figure
    price = config.PRICES.get(model) or config.PRICES.get(model.split("/")[-1])
    return None if not price else (tok_in * price[0] + tok_out * price[1]) / 1e6


def _call(model: str, parts: list, max_tokens: int) -> dict:
    """parts: list of str (text) or bytes (JPEG), in order. Returns text + usage."""
    b64 = lambda j: base64.b64encode(j).decode()  # noqa: E731
    if config.PROVIDER == "anthropic":
        content = [{"type": "text", "text": p} if isinstance(p, str) else
                   {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                "data": b64(p)}} for p in parts]
        r = _post(ANTHROPIC_URL, timeout=90, json={
            "model": model, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "user", "content": content}]},
            headers={"x-api-key": config.API_KEY, "anthropic-version": "2023-06-01"})
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        u = data.get("usage") or {}
        tin, tout = u.get("input_tokens", 0), u.get("output_tokens", 0)
        return {"text": text, "tok_in": tin, "tok_out": tout, "usd": _usd(model, tin, tout)}

    content = [{"type": "text", "text": p} if isinstance(p, str) else
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64(p)}}
               for p in parts]
    r = _post(OPENROUTER_URL, timeout=90, json={
        "model": model, "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens, "temperature": 0, "usage": {"include": True},
        "reasoning": config.reasoning(model)},   # no paid hidden thinking for tiny JSON
        headers={"Authorization": f"Bearer {config.API_KEY}"})
    data = r.json()
    u = data.get("usage") or {}
    tin, tout = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    return {"text": data["choices"][0]["message"].get("content") or "",
            "tok_in": tin, "tok_out": tout, "usd": _usd(model, tin, tout, u.get("cost"))}


def _json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences; take the outer {...}."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def _cached_or_call(k: str, model: str, run_mock, run_live) -> dict:
    hit = cache.get("vision", k)
    if hit is not None:
        # A cached answer is free: report zero cost for this call.
        return {**hit, "cached": True, "usd": 0.0, "tok_in": 0, "tok_out": 0, "ms": 0}
    t0 = time.perf_counter()
    out = run_mock() if config.MOCK else run_live()
    out.update(ms=int((time.perf_counter() - t0) * 1000), model=model, mock=config.MOCK)
    cache.put("vision", k, out)
    return {**out, "cached": False}


def image_tokens(w: int, h: int) -> int:
    """Claude's visual-token rule: one token per 28x28 pixel patch."""
    return math.ceil(w / 28) * math.ceil(h / 28)


# ---------------- single photo: yes / no / unclear ----------------
def _prompt(questions: list[dict]) -> str:
    lines = "\n".join(f"{q['id']}: {q['q']}" for q in questions)
    return ("Photo of a building, checked for an insurer. For each id answer "
            "y (yes), n (no) or u (unclear / not visible). Add conf = your overall "
            "confidence 0-1. Reply with JSON only, e.g. {\"door_low\":\"n\",\"conf\":0.8}\n"
            + lines)


def parse(text: str, ids: list[str]) -> tuple[dict, float]:
    data = _json(text)
    answers = {}
    for i in ids:
        v = str(data.get(i, "u")).strip().lower()[:1]
        answers[i] = v if v in ANSWERS else "u"   # anything odd counts as unclear
    try:
        conf = min(1.0, max(0.0, float(data.get("conf", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return answers, conf


def ask(model: str, jpeg: bytes, questions: list[dict]) -> dict:
    ids = [q["id"] for q in questions]
    k = cache.key(model, hashlib.sha1(jpeg).hexdigest(), ",".join(ids), str(config.MOCK))

    def mock():
        # Deterministic fake answers from the image bytes: same photo -> same answers.
        h = hashlib.sha1(jpeg).digest()
        return {"answers": {i: "ynu"[h[n % len(h)] % 3] for n, i in enumerate(ids)},
                "conf": 0.4 + (h[-1] % 60) / 100, "tok_in": 0, "tok_out": 0, "usd": 0.0}

    def live():
        r = _call(model, [_prompt(questions), jpeg], config.MAX_OUT_TOKENS)
        answers, conf = parse(r["text"], ids)
        return {"answers": answers, "conf": conf, "tok_in": r["tok_in"],
                "tok_out": r["tok_out"], "usd": r["usd"]}

    return _cached_or_call(k, model, mock, live)


# ---------------- video frames: find objects ----------------
# Bump when the prompt changes, so old cached answers to the old prompt are not reused.
FIND_PROMPT_VERSION = "2"
_BOX_TEXT = {"yx": "[ymin, xmin, ymax, xmax]", "xy": "[xmin, ymin, xmax, ymax]"}
_BOX_EXAMPLE = {"yx": "[120,300,380,720]", "xy": "[300,120,720,380]"}


def _find_prompt(n: int, kinds: list[str], order: str = "yx") -> str:
    lines = "\n".join(f"{k}: {CATALOGUE[k]['find']}" for k in kinds)
    # 'u' is only for frames that cannot be judged: in our test a cheap model marked every
    # clear frame with no target object as unclear, which sent all frames to the strong model.
    return (f"The {n} images above are frames 0-{n - 1} of a walk-around video of a business "
            "site, checked for hail and flood prevention. Find ONLY these object types:\n"
            f"{lines}\n"
            "For each object give f = frame number, t = type, "
            f"b = box {_BOX_TEXT[order]} scaled 0-1000, c = confidence 0-1. "
            "u = list of frames too dark, blurred or blocked to judge; a clear frame without "
            "these objects is not unclear. At most 5 objects per frame. "
            "Reply with JSON only, no other text, e.g. "
            f'{{"o":[{{"f":0,"t":"glass_roof","b":{_BOX_EXAMPLE[order]},"c":0.8}}],"u":[]}}')


def _find_json(text: str) -> dict:
    """The reply as a dict. If the JSON is broken (most often cut off at the token limit),
    keep every complete {...} object entry rather than losing the whole answer."""
    data = _json(text)
    if _pick(data, "o", "objects", "detections", "u", "unclear") is not None:
        return data
    # Also covers a bare list of objects, e.g. Gemini's own [{"box_2d": ..., "label": ...}].
    entries = [_json(m) for m in re.findall(r"\{[^{}]*\}", text or "")]
    return {"o": [e for e in entries if e]}


def _pick(d: dict, *names):
    # Models rename keys ('f' / 'frame', 'b' / 'box' / 'bbox'...); take the first one present.
    return next((d[k] for k in names if k in d), None)


def _box_numbers(b, order: str) -> list[float] | None:
    """Box as [x0, y0, x1, y1] in the model's own scale, or None if unreadable."""
    if isinstance(b, dict):   # {"xmin":..} / {"x0":..} names say the axis, no order needed
        vals = [_pick(b, *ks) for ks in (("xmin", "x0"), ("ymin", "y0"),
                                         ("xmax", "x1"), ("ymax", "y1"))]
    elif isinstance(b, (list, tuple)) and len(b) == 4:
        vals = [b[1], b[0], b[3], b[2]] if order == "yx" else list(b)
    else:
        return None
    try:
        return [float(v) for v in vals]
    except (TypeError, ValueError):
        return None


def _to_fraction(box: list[float], size: tuple[int, int] | None) -> tuple | None:
    """0-1 fractions, 0-1000, or pixels -> 0-1 fractions; swapped corners are put in order."""
    x0, y0, x1, y1 = box
    top = max(box)
    if top <= 1.0:
        sx = sy = 1.0                      # already fractions
    elif top <= 1000 or not size:
        sx = sy = 1000.0                   # what we asked for
    else:
        sx, sy = size                      # pixels: only detectable above 1000
    x0, x1 = sorted((x0 / sx, x1 / sx))
    y0, y1 = sorted((y0 / sy, y1 / sy))
    clamp = lambda v: min(1.0, max(0.0, v))  # noqa: E731
    out = (clamp(x0), clamp(y0), clamp(x1), clamp(y1))
    return out if out[2] > out[0] and out[3] > out[1] else None


def _object(o, n: int, kinds: list[str], order: str, sizes) -> dict | None:
    """One well-formed object, or None: a bad entry is dropped, never guessed."""
    if not isinstance(o, dict):
        return None
    try:
        f = int(_pick(o, "f", "frame"))
        t = str(_pick(o, "t", "type", "kind", "label"))
        c = _pick(o, "c", "conf", "confidence")
        c = 0.5 if c is None else float(c)
    except (TypeError, ValueError):
        return None
    if not (0 <= f < n and t in kinds):
        return None
    nums = _box_numbers(_pick(o, "b", "box", "bbox", "box_2d"), order)
    box = nums and _to_fraction(nums, sizes[f] if sizes else None)
    if not box:
        return None
    return {"f": f, "kind": t, "box": box, "conf": round(min(1.0, max(0.0, c)), 2)}


def parse_find(text: str, n: int, kinds: list[str], order: str = "yx",
               sizes: list[tuple[int, int]] | None = None) -> tuple[list[dict], list[int]]:
    """Objects as {"f", "kind", "box": (x0, y0, x1, y1) as 0-1 fractions, "conf"},
    plus the frames the model could not judge."""
    data = _find_json(text)
    raw = _pick(data, "o", "objects", "detections") or []
    objs = [ob for ob in (_object(o, n, kinds, order, sizes) for o in raw) if ob]
    unclear = sorted({int(u) for u in _pick(data, "u", "unclear") or []
                      if str(u).strip().isdigit() and int(u) < n})
    return objs, unclear


def _sizes(jpegs: list[bytes]) -> list[tuple[int, int]]:
    # Only needed to read pixel boxes; PIL reads the size from the header, no decoding.
    return [Image.open(io.BytesIO(j)).size for j in jpegs]


def find(model: str, jpegs: list[bytes], kinds: list[str]) -> dict:
    """Asks `model`; if it stays busy or fails, the similar models in config.FALLBACKS.
    The answer's "model" says which one really answered (shown on the details page)."""
    tried = [model, *config.FALLBACKS.get(model, [])]
    for i, m in enumerate(tried):
        try:
            return _find_one(m, jpegs, kinds)
        except requests.RequestException:
            if i == len(tried) - 1:
                raise


def _find_one(model: str, jpegs: list[bytes], kinds: list[str]) -> dict:
    n = len(jpegs)
    order = config.box_order(model)
    k = cache.key(model, *(hashlib.sha1(j).hexdigest() for j in jpegs), ",".join(kinds),
                  str(config.MOCK), FIND_PROMPT_VERSION, order)

    def mock():
        # Fake but stable objects, clearly labelled MOCK in the app.
        objs = []
        for f, j in enumerate(jpegs):
            h = hashlib.sha1(j).digest()
            for m in range(h[0] % 3):
                y, x = 100 + h[m + 1] % 500, 100 + h[m + 4] % 600
                objs.append({"f": f, "kind": kinds[h[m + 7] % len(kinds)],
                             "box": (x / 1000, y / 1000, (x + 250) / 1000, (y + 250) / 1000),
                             "conf": round(0.45 + (h[m + 10] % 50) / 100, 2)})
        return {"objects": objs, "unclear": [], "tok_in": 0, "tok_out": 0, "usd": 0.0}

    def live():
        parts: list = []
        for i, j in enumerate(jpegs):
            parts += [f"Frame {i}:", j]
        parts.append(_find_prompt(n, kinds, order))
        r = _call(model, parts, config.FIND_MAX_OUT)
        objs, unclear = parse_find(r["text"], n, kinds, order, _sizes(jpegs))
        return {"objects": objs, "unclear": unclear, "tok_in": r["tok_in"],
                "tok_out": r["tok_out"], "usd": r["usd"]}

    return _cached_or_call(k, model, mock, live)

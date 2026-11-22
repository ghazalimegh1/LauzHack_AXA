"""Talking to vision models through OpenRouter, reliably and cheaply.

- Busy (429) or broken (5xx) answers are retried after 2 s, then after 5 s.
- If a model still fails, the same request goes to a similar fallback model.
- All tries together stop after settings.AI_TOTAL_S seconds.
- Every answer is cached on disk, so running the same check again costs nothing.
- The API key is read from the environment at call time and is never logged or returned.
"""
from __future__ import annotations

import base64
import json
import math
import re
import time

import requests

from . import cache, settings

URL = "https://openrouter.ai/api/v1/chat/completions"


class AIError(Exception):
    """No model could answer. The message is safe to log (no key, no request body)."""


def _content(parts: list) -> list:
    out = []
    for p in parts:
        if isinstance(p, bytes):
            b64 = base64.b64encode(p).decode("ascii")
            out.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        else:
            out.append({"type": "text", "text": str(p)})
    return out


def _http_post(model: str, parts: list, max_tokens: int, timeout=None):
    """One HTTP request. Returns (status code or None for a network error, json or None)."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": _content(parts)}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "reasoning": {"enabled": False},   # hidden thinking is billed and not needed here
        "usage": {"include": True},        # OpenRouter then reports the real cost
    }
    headers = {"Authorization": f"Bearer {settings.api_key()}", "X-Title": "Site Check AXA"}
    try:
        r = requests.post(URL, json=body, headers=headers, timeout=timeout or settings.AI_TIMEOUT_S)
    except requests.RequestException:
        return None, None
    try:
        data = r.json()
    except ValueError:
        data = None
    return r.status_code, data


def _retryable(status) -> bool:
    return status is None or status == 429 or (isinstance(status, int) and status >= 500)


def price(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = settings.PRICES.get(model, (0.0, 0.0))
    return tokens_in * p_in / 1e6 + tokens_out * p_out / 1e6


def _from_cache(hit: dict) -> dict:
    """A reused answer costs nothing now, but we keep what the first run was billed so the
    page can still show a real cost. Old entries without a cost give None (unknown), not 0."""
    first_usd = hit.get("usd")
    return {"text": hit["text"], "model": hit["model"], "tokens_in": 0, "tokens_out": 0,
            "usd": 0.0, "billed": True, "cached": True, "attempts": [],
            "first_run_usd": float(first_usd) if isinstance(first_usd, (int, float)) else None,
            "first_run_billed": bool(hit.get("billed", first_usd is not None)),
            "first_run_tokens_in": hit.get("tokens_in"),
            "first_run_tokens_out": hit.get("tokens_out")}


def ask(model: str, parts: list, max_tokens: int, post=None, sleep=time.sleep,
        use_cache: bool = True, clock=time.monotonic) -> dict:
    """Sends text and JPEG images (in order) and returns
    {"text", "model", "tokens_in", "tokens_out", "usd", "billed", "cached", "attempts"},
    plus "first_run_usd", "first_run_tokens_in/out" when the answer came from the cache.
    use_cache=False skips reading the cache (a fresh, paid answer) but still saves it.
    Raises AIError when every model in the chain failed or the time budget ran out."""
    deadline = clock() + settings.AI_TOTAL_S
    # A request may not run past the deadline either.
    post = post or (lambda m, p, t: _http_post(m, p, t, timeout=max(1.0, deadline - clock())))
    chain = [model] + settings.FALLBACKS.get(model, [])
    key = cache.make_key("v1", model, max_tokens, *parts)
    hit = cache.get("ai", key) if use_cache else None
    if hit is not None and hit.get("text"):
        return _from_cache(hit)
    attempts = []
    for m in chain:
        waits = (0,) + tuple(settings.RETRY_WAITS_S)
        for wait in waits:
            if clock() + wait >= deadline:
                attempts.append({"model": m, "status": "out of time"})
                raise AIError("No model answered in time: "
                              + ", ".join(f"{a['model']} {a['status']}" for a in attempts))
            if wait:
                sleep(wait)
            status, data = post(m, parts, max_tokens)
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                status = err.get("code") if isinstance(err.get("code"), int) else (status or 502)
                if status == 200:
                    status = 502
            text = _text(data) if status == 200 else None
            if status == 200 and text is not None:
                usage = data.get("usage") or {}
                t_in = int(usage.get("prompt_tokens") or 0)
                t_out = int(usage.get("completion_tokens") or 0)
                usd = usage.get("cost")
                # billed=False marks a cost we had to work out from the price list ourselves
                billed = isinstance(usd, (int, float))
                usd = float(usd) if billed else price(m, t_in, t_out)
                attempts.append({"model": m, "status": 200})
                out = {"text": text, "model": m, "tokens_in": t_in, "tokens_out": t_out,
                       "usd": usd, "billed": billed, "cached": False, "attempts": attempts}
                cache.put("ai", key, {k: v for k, v in out.items() if k not in ("cached", "attempts")})
                return out
            attempts.append({"model": m, "status": status})
            if status == 200:          # answered, but with no usable text: treat as broken
                status = 502
            if not _retryable(status):
                break                  # e.g. 400: retrying the same model will not help
    raise AIError("No model answered: " + ", ".join(f"{a['model']} {a['status']}" for a in attempts))


def _text(data):
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if isinstance(content, list):   # some providers return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content if isinstance(content, str) and content.strip() else None


def parse_json(text: str) -> dict:
    """Model text -> dict. Accepts code fences and extra words around the JSON."""
    t = re.sub(r"```(?:json)?", "", text or "").strip()
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the answer")
    return json.loads(t[start:end + 1])


# ---------------- the estimate rule (same for all three designs) ----------------
# Image tokens follow Google's documented rule for Gemini: an image up to 384 px on both
# sides is 258 tokens; a larger one is cut into 768 x 768 tiles of 258 tokens each.
PROMPT_TOKENS = 400        # instructions per call (our prompt is about this long)
OUT_TOKENS_PER_FRAME = 40  # a short JSON entry per frame
PRO_THINKING_TOKENS = 128  # Gemini 2.5 Pro cannot switch thinking off; 128 is its minimum


def image_tokens(w: int, h: int) -> int:
    if w <= 384 and h <= 384:
        return 258
    return math.ceil(w / 768) * math.ceil(h / 768) * 258


def estimate(model: str, sizes: list, calls: int) -> dict:
    """Estimated tokens and USD for sending images of these (w, h) sizes in `calls` calls."""
    if not sizes or calls <= 0:
        return {"tokens_in": 0, "tokens_out": 0, "usd": 0.0}
    t_in = calls * PROMPT_TOKENS + sum(image_tokens(w, h) for w, h in sizes)
    t_out = len(sizes) * OUT_TOKENS_PER_FRAME
    if model == settings.BASELINE_MODEL:
        t_out += calls * PRO_THINKING_TOKENS
    return {"tokens_in": t_in, "tokens_out": t_out, "usd": price(model, t_in, t_out)}

"""A tiny JSON-on-disk cache. Asking the same question twice should cost nothing,
which also makes a repeated live demo free and fast."""
from __future__ import annotations

import hashlib
import json
import os

from . import config


def key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _path(name: str):
    config.CACHE_DIR.mkdir(exist_ok=True)
    return config.CACHE_DIR / f"{name}.json"


def get(name: str, k: str):
    if os.environ.get("FRUGAL_NO_CACHE") == "1" and name == "vision":
        return None  # the benchmark must pay for every call to measure honestly
    p = _path(name)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get(k)
    except json.JSONDecodeError:
        return None  # a broken cache file must never break the app


def put(name: str, k: str, value) -> None:
    p = _path(name)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        data = {}
    data[k] = value
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

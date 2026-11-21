"""A tiny file cache: the same question is never paid for twice."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import settings


def make_key(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:40]


def _path(area: str, key: str) -> Path:
    return settings.CACHE_DIR / area / f"{key}.json"


def get(area: str, key: str):
    p = _path(area, key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def put(area: str, key: str, value) -> None:
    p = _path(area, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value), encoding="utf-8")

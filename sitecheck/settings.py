"""Every setting in one place, so the team can change a model or a threshold without
touching the logic."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "v2"
WEB_OUT = ROOT / "web" / "out"
DETECTOR_WEIGHTS = ROOT / "models" / "yolo11n.pt"


def _detector_label(weights: Path) -> str:
    """'yolo11n.pt' -> 'YOLO11n'. Taken from the file name, so the label shown on the
    website can never drift from the model that is really loaded."""
    stem = weights.stem
    return "YOLO" + stem[4:] if stem.lower().startswith("yolo") else stem


DETECTOR_LABEL = _detector_label(DETECTOR_WEIGHTS)


def _read_dotenv(path: Path) -> None:
    """Loads KEY=value lines from .env into the environment. Never prints anything."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip("'\""))


_read_dotenv(ROOT / ".env")


def api_key() -> str:
    """Read on demand, never stored in results, logs or files."""
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def ai_enabled() -> bool:
    return bool(api_key()) and os.environ.get("SITECHECK_NO_AI") != "1"


# ---------------- models (OpenRouter ids) ----------------
CHEAP_MODEL = "google/gemini-2.5-flash-lite"
STRONG_MODEL = "google/gemini-2.5-flash"
BASELINE_MODEL = "google/gemini-2.5-pro"    # only used to estimate the comparison
# If a model stays busy or fails, the same request goes to the next model in its list.
FALLBACKS = {
    CHEAP_MODEL: ["google/gemini-3.1-flash-lite", "google/gemini-2.5-flash"],
    STRONG_MODEL: ["google/gemini-3.1-flash-lite"],
}
RETRY_WAITS_S = (2, 5)      # wait 2 s, then 5 s, before giving up on a model
HTTP_TIMEOUT_S = 25
AI_TIMEOUT_S = 60
# All tries for one question together stop after this, so a dead network cannot hold the
# queue for minutes (3 models x 3 tries x 60 s was up to 9 minutes).
AI_TOTAL_S = 90

# USD per 1 million tokens (input, output), read from https://openrouter.ai/api/v1/models
# on 2026-11-21. OpenRouter also reports the real cost of every call; these prices are
# only used for the estimate and the comparison.
PRICES = {
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    "google/gemini-3.1-flash-lite": (0.25, 1.50),
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-2.5-pro": (1.25, 10.00),
}

# ---------------- image sizes (longest side, pixels) ----------------
CHEAP_IMG_PX = 512          # small images: enough to see roofs, windows and pallets
STRONG_IMG_PX = 768         # a second look gets more detail
NAIVE_FRAME = (1280, 720)   # "HD" frame of the naive design in the comparison

# ---------------- video ----------------
SAMPLES_PER_S = 2           # keep 2 frames per second of video
MAX_SAMPLES = 360           # very long videos: wider spacing instead of more work
KEYFRAMES_DEFAULT = 6
KEYFRAMES_MIN, KEYFRAMES_MAX = 4, 10
WORK_PX = 960               # frames are kept at this size in memory

# ---------------- AI answers ----------------
UNSURE_BELOW = 0.6          # confidence below this: the strong model takes a second look,
                            # and if it is still below, the finding is "uncertain"
CHEAP_MAX_OUT = 900         # output tokens: a short JSON list, never prose
STRONG_MAX_OUT = 700

# ---------------- risk colours (shared with the website via /api/info) ----------------
RISK_COLOURS = {"high": "#C62828", "medium": "#E8710A", "low": "#F2A900",
                "not relevant here": "#8A8A8A", "uncertain": "#5F5F5F"}

MAX_JOBS = 5                # jobs kept in memory; older ones are dropped with their video

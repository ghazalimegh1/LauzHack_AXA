"""All settings in one place, so the team can swap models or thresholds
without touching any logic."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"


def _load_dotenv(path: Path) -> None:
    # Tiny .env reader: saves a dependency for five lines of work.
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

# Two ways to reach a vision service. An Anthropic key wins if both are set.
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
PROVIDER = os.environ.get("PROVIDER") or (
    "anthropic" if ANTHROPIC_KEY else "openrouter" if OPENROUTER_KEY else "mock")
API_KEY = ANTHROPIC_KEY if PROVIDER == "anthropic" else OPENROUTER_KEY
# No key -> mock mode, so the app always starts (useful offline and for tests).
MOCK = PROVIDER == "mock" or not API_KEY or os.environ.get("FRUGAL_MOCK") == "1"

# Cheap model answers first; the strong one only sees what the cheap one could not decide.
_DEFAULTS = {
    "anthropic": ("claude-haiku-5-5", "claude-sonnet-5-5"),
    # Qwen handles the first pass; GPT-4o is reserved for important uncertain findings.
    "openrouter": ("qwen/qwen3-vl-8b-instruct", "openai/gpt-4o"),
    "mock": ("mock-cheap", "mock-strong"),
}
CHEAP_MODEL = os.environ.get("CHEAP_MODEL") or _DEFAULTS.get(PROVIDER, _DEFAULTS["mock"])[0]
STRONG_MODEL = os.environ.get("STRONG_MODEL") or _DEFAULTS.get(PROVIDER, _DEFAULTS["mock"])[1]
# The "send everything to a top model" design we compare against. Kept separate from
# STRONG_MODEL so a cheaper comparison model does not make the escalation path look cheap too.
NAIVE_MODEL = os.environ.get("NAIVE_MODEL") or (
    "google/gemini-2.5-flash-lite" if PROVIDER == "openrouter" else "claude-sonnet-5-5")

# USD per 1M tokens (input, output). OpenRouter reports real cost itself;
# the Claude API does not, so these are used there.
# OpenRouter prices supplied for the current model strategy.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),     # prompts up to 100k tokens
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "anthropic/claude-haiku-5.5": (0.10, 0.50),     # OpenRouter writes 5.5, not 5-5
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),
    "qwen/qwen3-vl-8b-instruct": (0.117, 0.455),
    "openai/gpt-4o": (2.50, 10.00),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    "google/gemini-3.1-flash-lite": (0.25, 1.50),
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-2.5-pro": (1.25, 10.00),
}


def box_order(model: str) -> str:
    """Which box order we ask a model for, and parse its answer in. The order cannot be
    detected from the numbers, so prompt and parser always use this same setting.
    'yx' = [ymin, xmin, ymax, xmax] 0-1000: Gemini is trained on this order.
    'xy' = [xmin, ymin, xmax, ymax] 0-1000: tested 2026-11-21 on two site photos, Claude
    Haiku 5.5 put its boxes in the sky when asked for 'yx', and near the right objects
    (though loose) when asked for 'xy'."""
    return os.environ.get("BOX_ORDER") or ("yx" if "gemini" in model.lower() else "xy")


def reasoning(model: str) -> dict:
    """Keep hidden reasoning off because the vision response is intentionally tiny JSON."""
    if "gemini" in model and "pro" in model:
        return {"max_tokens": 128}
    return {"enabled": False}

CHEAP_IMG_PX = 512      # small image = few image tokens; enough to see windows and roofs
STRONG_IMG_PX = 768     # escalation gets a bit more detail, not the full photo
NAIVE_IMG_PX = 1536     # what a "send everything" approach would typically send
MAX_OUT_TOKENS = 120    # the answer is a short JSON, never an essay
CONF_MIN = 0.6          # below this, the cheap model's answer is not trusted
HTTP_TIMEOUT = 25

# --- video ---
SAMPLE_EVERY_S = 0.5    # look at 2 frames per second; neighbours are near-identical anyway
MAX_SAMPLES = 240       # long videos get a wider step instead of more work
KEYFRAMES = 6           # frames that may reach a paid model
FIND_MAX_OUT = 700      # object list for all frames in one reply
DETECTOR = ROOT / "models" / "yolo11n.pt"   # free local detector, 5 MB, downloads once

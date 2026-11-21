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

# Two ways to reach a model. A Claude key wins if both are set.
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
    # Strong = 2.5 Flash, not Pro: on our box test (2 site photos, 2026-11-21) Flash drew the
    # same boxes as Pro (skylight, glass band, 5 trucks) for USD 0.00083 instead of 0.00466.
    # Qwen3-VL 8B + GPT-4o were tried on 2026-11-21 (iPhone night walk, same 6 key frames):
    # they found only what the free detector had found, for USD 0.0076 instead of 0.0013.
    "openrouter": ("google/gemini-2.5-flash-lite", "google/gemini-2.5-flash"),
    "mock": ("mock-cheap", "mock-strong"),
}
CHEAP_MODEL = os.environ.get("CHEAP_MODEL") or _DEFAULTS.get(PROVIDER, _DEFAULTS["mock"])[0]
STRONG_MODEL = os.environ.get("STRONG_MODEL") or _DEFAULTS.get(PROVIDER, _DEFAULTS["mock"])[1]
# The "send everything to a top model" design we compare against. Kept separate from
# STRONG_MODEL so a cheaper escalation model does not make the naive design look cheap too.
# It must be the top model of the family: comparing against a cheaper one would be meaningless.
NAIVE_MODEL = os.environ.get("NAIVE_MODEL") or (
    "google/gemini-2.5-pro" if PROVIDER == "openrouter" else "claude-sonnet-5-5")

# USD per 1M tokens (input, output). OpenRouter reports real cost itself;
# the Claude API does not, so these are used there (docs pricing page, Nov 2026).
# The OpenRouter rows were read from https://openrouter.ai/api/v1/models on 2026-11-21.
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
    """OpenRouter 'reasoning' setting per model. Hidden thinking is billed as output:
    measured 2026-11-21, Claude Haiku 5.5 spent 260 of 274 output tokens thinking and then
    returned no objects; Gemini 2.5 Pro used up the whole 700-token budget thinking and the
    answer was cut off. A short JSON list needs no thinking. Gemini 2.5 Pro cannot switch
    thinking off, so it gets the smallest budget instead (128 worked in our test)."""
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

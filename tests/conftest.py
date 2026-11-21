import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SITECHECK_NO_AI", "1")     # tests never pay for AI

from sitecheck import settings  # noqa: E402


@pytest.fixture(autouse=True)
def temp_cache(tmp_path, monkeypatch):
    """Every test gets its own empty cache folder."""
    monkeypatch.setattr(settings, "CACHE_DIR", tmp_path / "cache")
    yield

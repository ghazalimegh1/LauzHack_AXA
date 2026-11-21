"""No API key may appear in any project file (code, built website, README...).
The key value is never printed: a failure only names the file."""
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", ".next", "cache", "models", "eval", "__pycache__",
             ".pytest_cache"}
KEY_SHAPE = re.compile(rb"sk-or-v1-[0-9a-f]{20,}")


def project_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not SKIP_DIRS & set(path.relative_to(ROOT).parts) and path.name != ".env":
            yield path


def test_gitignore_protects_env():
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in lines
    example = (ROOT / ".env.example").read_text()
    assert re.search(r"^OPENROUTER_API_KEY=\s*$", example, re.M)


def test_env_is_not_tracked_by_git():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout
    assert ".env" not in tracked.splitlines()


def test_no_key_in_any_file():
    real = os.environ.get("OPENROUTER_API_KEY", "").strip().encode()
    bad = []
    for path in project_files():
        data = path.read_bytes()
        if KEY_SHAPE.search(data) or (len(real) > 10 and real in data):
            bad.append(str(path.relative_to(ROOT)))
    assert not bad, f"API key found in: {bad}"

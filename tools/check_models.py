"""Checks that the models in your settings exist and shows prices.
    python tools/check_models.py
With a Claude key: lists the Claude models your key can use.
Otherwise: lists the cheapest OpenRouter models that accept images
(Claude models there are named like anthropic/claude-...)."""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frugal import config  # noqa: E402

print(f"Provider: {config.PROVIDER}   cheap: {config.CHEAP_MODEL}   strong: {config.STRONG_MODEL}"
      f"   naive baseline: {config.NAIVE_MODEL}\n")

if config.PROVIDER == "anthropic":
    r = requests.get("https://api.anthropic.com/v1/models", timeout=30,
                     headers={"x-api-key": config.API_KEY, "anthropic-version": "2023-06-01"})
    r.raise_for_status()
    ids = [m["id"] for m in r.json()["data"]]
    print("\n".join(ids))
else:
    data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    rows = []
    for m in data:
        if "image" not in ((m.get("architecture") or {}).get("input_modalities") or []):
            continue
        p = m.get("pricing") or {}
        try:
            cin, cout = float(p.get("prompt", 0)) * 1e6, float(p.get("completion", 0)) * 1e6
        except ValueError:
            continue
        if cin > 0:  # skip free/preview entries: they are often rate-limited
            rows.append((cin, cout, m["id"]))
    print(f"{'USD in/1M':>10} {'USD out/1M':>11}  model id")
    for cin, cout, mid in sorted(rows)[:25]:
        print(f"{cin:10.3f} {cout:11.3f}  {mid}")
    print("\nClaude models on OpenRouter:")
    for cin, cout, mid in sorted(rows):
        if mid.startswith("anthropic/"):
            print(f"{cin:10.3f} {cout:11.3f}  {mid}")
    ids = [r[2] for r in rows]

for want in (config.CHEAP_MODEL, config.STRONG_MODEL, config.NAIVE_MODEL):
    known = "price known" if want in config.PRICES else "no price in config.PRICES (OpenRouter reports cost itself)"
    print(f"\n{want}: {'available, ' + known if want in ids else 'NOT FOUND - change it in .env'}")

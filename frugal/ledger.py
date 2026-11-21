"""Records every step with its cost, so frugality is measured and shown, not claimed."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Step:
    name: str
    kind: str            # "free", "ai", or "skipped"
    model: str = ""
    tok_in: int = 0
    tok_out: int = 0
    usd: float = 0.0
    ms: int = 0
    note: str = ""


@dataclass
class Ledger:
    steps: list[Step] = field(default_factory=list)

    def add(self, **kw) -> None:
        self.steps.append(Step(**kw))

    def totals(self) -> dict:
        ai = [s for s in self.steps if s.kind == "ai"]
        return {
            "ai_calls": sum(1 for s in ai if "cache" not in s.note),
            "tokens": sum(s.tok_in + s.tok_out for s in ai),
            "usd": sum(s.usd or 0.0 for s in ai),
            "ms": sum(s.ms for s in self.steps),
            "skipped": sum(1 for s in self.steps if s.kind == "skipped"),
        }

    def rows(self) -> list[dict]:
        return [asdict(s) for s in self.steps]

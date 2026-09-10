from __future__ import annotations

import json
import re
from pathlib import Path

from briefing.config import Config

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

# Deterministic stand-ins for the scorer's judgement, so the filter pipeline can be
# exercised without an API key. Order matters: first match wins.
_CATEGORY_HINTS = (
    ("pib", ("ministry", "cabinet", "pib", "government", "sebi", "press information")),
    ("macro", ("rbi", "repo", "inflation", "gdp", "cpi", "fiscal", "rupee", "crude", "yield")),
    ("global", ("fed", "boj", "nasdaq", "s&p", "treasury", "dollar index", "wall street")),
    ("mna", ("buyback", "demerger", "merger", "acquisition", "stake sale", "open offer")),
    ("microcap", ("order win", "bags order", "block deal", "bulk deal", "capacity expansion")),
    ("earnings", ("results", "profit", "revenue", "margin", "guidance", "concall", "earnings")),
)

_STRONG = ("buyback", "demerger", "merger", "order win", "block deal", "rbi", "repo",
           "gdp", "inflation", "profit", "results", "guidance", "acquisition")


class StubProvider:
    """Offline provider used by dry runs and tests.

    Generation returns a canned report from tests/fixtures/<prompt>_output.txt.
    Scoring applies a keyword heuristic and emits the same JSON shape the real scorer
    prompt specifies, so parsing, batching and threshold logic are all exercised.
    """

    name = "stub"

    def __init__(self, config: Config, prompt_name: str = "evening") -> None:
        self.config = config
        self.prompt_name = prompt_name

    def complete(self, system: str, user: str, tier: str) -> str:
        if tier == "score":
            return self._score(user)
        canned = FIXTURES / f"{self.prompt_name}_output.txt"
        if canned.exists():
            return canned.read_text(encoding="utf-8")
        return (
            f"[stub provider: no fixture at {canned.name}]\n"
            f"system prompt: {len(system)} chars, payload: {len(user)} chars\n"
        )

    @staticmethod
    def _score(listing: str) -> str:
        results = []
        for line in listing.splitlines():
            match = re.match(r"\s*(\d+)\.\s*(.+)", line)
            if not match:
                continue
            index, text = int(match.group(1)), match.group(2).lower()

            category = "uncategorised"
            for label, hints in _CATEGORY_HINTS:
                if any(h in text for h in hints):
                    category = label
                    break

            hits = sum(1 for keyword in _STRONG if keyword in text)
            score = 0 if category == "uncategorised" else min(10, 6 + hits)
            results.append(
                {"id": index, "score": score, "category": category, "reason": "stub heuristic"}
            )
        return json.dumps(results)

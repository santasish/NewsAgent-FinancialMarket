"""End-to-end run: fetch -> compute -> filter -> payload -> generate -> verify.

Delivery is driven by the CLI once the briefing is on disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from briefing.config import Config
from briefing.fetch import news as news_fetch
from briefing.fetch.base import FetchResult, save_raw
from briefing.filter import apply_caps, rule_filter, score_items
from briefing.generate import generate
from briefing.llm.base import Provider
from briefing.payload import BUILDERS, PayloadContext
from briefing.payload.common import OPTIONAL_SOURCES
from briefing.sources import fetch_all
from briefing.verify import VerifyResult, verify, violations_feedback

VERIFICATION_BANNER = (
    "A note before we start: some figures in this issue could not be matched to the "
    "source data, so treat the numbers with care."
)

# Text-shaped feeds, with the plain name the issue uses when one is down. A failure
# here does not blank a section outright, but it does mean thinner coverage, so the
# run is marked degraded and the issue says so.
NEWS_SOURCES = {
    "news.google_rss": "press headlines",
    "nse.announcements": "company filings from the NSE",
    "bse.announcements": "company filings from the BSE",
    "pib.releases": "government releases",
}


@dataclass
class RunResult:
    prompt_name: str
    payload: dict[str, Any]
    output: str
    verification: VerifyResult
    fetches: list[FetchResult] = field(default_factory=list)
    scored: list[dict[str, Any]] = field(default_factory=list)
    kept_news: list[dict[str, Any]] = field(default_factory=list)

    @property
    def failed_sources(self) -> list[str]:
        """Sources that should have worked and did not. Optional ones never count."""
        return [f.name for f in self.fetches if not f.ok and f.name not in OPTIONAL_SOURCES]

    @property
    def degraded(self) -> bool:
        return bool(self.payload.get("degraded"))


def gather_news(
    config: Config,
    provider: Provider,
    fetches: list[FetchResult],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rule-gate, score and cap everything text-shaped that was fetched."""
    items: list[dict[str, Any]] = []
    for name in NEWS_SOURCES:
        result = next((f for f in fetches if f.name == name), None)
        if result and result.ok and isinstance(result.data, list):
            items.extend(result.data)

    if not items:
        return [], []

    candidates, _ = rule_filter(items)
    kept, scored = score_items(config, provider, candidates)
    capped = apply_caps(kept, config.get("caps", {}))
    flattened = [item for group in capped.values() for item in group]
    flattened.sort(key=lambda i: i.get("score", 0), reverse=True)
    return flattened, scored


def run_pipeline(
    config: Config,
    provider: Provider,
    prompt_name: str,
    day: date,
    *,
    out_dir: Path,
    skip_news: bool = False,
) -> RunResult:
    fetches = fetch_all(config, include_news=not skip_news)

    news: list[dict[str, Any]] = []
    scored: list[dict[str, Any]] = []
    if not skip_news:
        news, scored = gather_news(config, provider, fetches)

    ctx = PayloadContext.from_results(fetches)
    for source_name, plain_name in NEWS_SOURCES.items():
        if source_name in OPTIONAL_SOURCES:
            continue
        result = next((f for f in fetches if f.name == source_name), None)
        if result is not None and not result.ok:
            ctx.missing.append(plain_name)

    payload = BUILDERS[prompt_name](ctx, day, news)

    save_raw(fetches, Path(config.get("raw_dir", "raw")), f"{day.isoformat()}_{prompt_name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{day.isoformat()}_{prompt_name}_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if scored:
        # Every headline with its score, so the threshold can be tuned against real days.
        audit = [
            {k: item.get(k) for k in ("score", "category", "score_reason", "headline", "subject", "company", "source")}
            for item in sorted(scored, key=lambda i: i.get("score", 0), reverse=True)
        ]
        (out_dir / f"{day.isoformat()}_{prompt_name}_scored.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    tolerance = config.get("verify.relative_tolerance", 0.001)
    min_magnitude = config.get("verify.min_magnitude", 100)

    output = generate(config, provider, prompt_name, payload)
    result = verify(output, payload, tolerance=tolerance, min_magnitude=min_magnitude)

    for _ in range(config.get("verify.max_regenerations", 1)):
        if result.ok:
            break
        corrected = dict(payload, _correction=violations_feedback(result))
        output = generate(config, provider, prompt_name, corrected)
        result = verify(output, payload, tolerance=tolerance, min_magnitude=min_magnitude)

    if not result.ok:
        output = f"{VERIFICATION_BANNER}\n\n{output}"

    return RunResult(
        prompt_name=prompt_name,
        payload=payload,
        output=output,
        verification=result,
        fetches=fetches,
        scored=scored,
        kept_news=news,
    )

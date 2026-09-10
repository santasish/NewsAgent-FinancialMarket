"""LLM relevancy scoring — the second gate after the keyword rules.

Each surviving headline gets a 0-10 market-impact score and a category label. Batching
keeps this to a handful of cheap calls per run. A batch whose response cannot be parsed
is scored 0 and excluded: an unscored item is never silently promoted into the briefing.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from briefing.config import Config
from briefing.generate import load_prompt
from briefing.llm.base import Provider

VALID_CATEGORIES = {"macro", "global", "earnings", "mna", "microcap", "pib"}

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)
_ARRAY = re.compile(r"\[.*\]", re.S)


SOURCE_TAGS = {"PIB": "[PIB]", "NSE": "[NSE filing]", "BSE": "[BSE filing]"}


def _describe(item: dict[str, Any]) -> str:
    """One line per item, tagged with where it came from.

    The tag matters: the scorer applies different standards to a government release, an
    exchange disclosure and a press headline, and cannot tell them apart otherwise.
    """
    headline = item.get("headline") or item.get("subject") or ""
    company = item.get("company")
    summary = (item.get("summary") or item.get("detail") or "").strip()
    tag = SOURCE_TAGS.get(str(item.get("source") or ""), "[press]")
    parts = [f"{tag} {company}: {headline}" if company else f"{tag} {headline}"]
    if summary:
        parts.append(summary[:200])
    return " — ".join(parts)


def _parse(response: str) -> list[dict[str, Any]]:
    text = _FENCE.sub("", response.strip())
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = _ARRAY.search(text)
        if not match:
            raise
        parsed = json.loads(match.group())
    if not isinstance(parsed, list):
        raise ValueError("scorer did not return a JSON array")
    return parsed


def _score_batch(
    config: Config,
    provider: Provider,
    system: str,
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    listing = "\n".join(f"{i}. {_describe(item)}" for i, item in enumerate(batch, start=1))

    try:
        parsed = _parse(provider.complete(system=system, user=listing, tier="score"))
    except Exception as first_error:
        try:
            retry_system = system + (
                "\n\nYour previous response was not valid JSON. Return ONLY the JSON array."
            )
            parsed = _parse(provider.complete(system=retry_system, user=listing, tier="score"))
        except Exception:
            return [
                dict(item, score=0, category="unscored", scoring_error=str(first_error)[:120])
                for item in batch
            ]

    by_id = {}
    for entry in parsed:
        if isinstance(entry, dict) and isinstance(entry.get("id"), int):
            by_id[entry["id"]] = entry

    out = []
    for index, item in enumerate(batch, start=1):
        entry = by_id.get(index, {})
        category = entry.get("category")
        try:
            score = int(entry.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        out.append(
            dict(
                item,
                score=max(0, min(10, score)),
                category=category if category in VALID_CATEGORIES else "uncategorised",
                score_reason=str(entry.get("reason", ""))[:120],
            )
        )
    return out


def score_items(
    config: Config,
    provider: Provider,
    items: Iterable[dict[str, Any]],
    *,
    batch_size: int | None = None,
    threshold: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Score every item; return (kept above threshold, all scored items)."""
    items = list(items)
    if not items:
        return [], []

    system = load_prompt(config, "scorer", require_core_rules=False)
    size = batch_size or config.get("scoring.batch_size", 20)
    cutoff = threshold if threshold is not None else config.get("scoring.threshold", 7)

    scored: list[dict[str, Any]] = []
    for start in range(0, len(items), size):
        scored.extend(_score_batch(config, provider, system, items[start : start + size]))

    kept = sorted(
        (i for i in scored if i["score"] >= cutoff),
        key=lambda i: i["score"],
        reverse=True,
    )
    return kept, scored

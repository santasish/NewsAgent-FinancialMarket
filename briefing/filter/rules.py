"""Cheap rule gate ahead of the LLM scorer.

Hundreds of headlines arrive per run and most are retail-facing filler. Dropping the
obvious noise here keeps the scoring cost down and stops junk from crowding out real
catalysts.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

HIGH_IMPACT_KEYWORDS = (
    # results and guidance
    "results", "profit", "revenue", "ebitda", "margin", "guidance", "concall",
    "earnings", "q1", "q2", "q3", "q4", "yoy", "quarter",
    # special situations
    "buyback", "demerger", "merger", "acquisition", "acquires", "stake sale",
    "open offer", "amalgamation", "restructuring", "delisting", "rights issue",
    "preferential", "fundraise", "qip", "ipo", "listing",
    # orders and capacity
    "order win", "bags order", "order book", "contract", "loi", "letter of intent",
    "capacity expansion", "capex", "plant", "commissioning",
    # deals and flows
    "block deal", "bulk deal", "stake", "promoter", "pledge", "fii", "dii",
    # macro and policy
    "rbi", "repo", "inflation", "cpi", "wpi", "gdp", "fiscal", "sebi", "tariff",
    "rate cut", "rate hike", "policy", "crude", "rupee", "yield", "fed", "boj",
    # regulatory and governance
    "sebi order", "penalty", "resignation", "ceo", "managing director", "board approves",
)

NOISE_PATTERNS = (
    r"\btop \d+\b",
    r"\bshould you (buy|sell|switch|invest)\b",
    r"\bstocks to (buy|watch)\b",
    r"\b(best|worst) \d+\b",
    r"\bhoroscope\b",
    r"\bmutual fund\b.*\b(sip|portfolio|switch)\b",
    r"\b(gold|silver) (rate|price) today\b",
    r"\bexplained\b.*\bfor beginners\b",
    r"\bwhat is\b.*\?$",
    r"\bhow to\b",
    r"\bopinion\b",
    r"\btechnical (view|picks)\b",
    r"\bmuhurat\b",
    # Personal finance and human-interest pieces mention profit and rupees without
    # touching a listed company. The scorer catches most of these; the gate saves the
    # call when the shape is unmistakable.
    r"\b(man|woman|farmer|couple|techie|engineer|student|teacher|retiree)\b.{0,40}\b(earns|makes|saves|built)\b",
    r"\bwhere should you\b",
    r"\bshould you\b.{0,30}\?",
    r"\bemergency (fund|money)\b",
    r"\bhome loan\b",
    r"\bcredit card\b",
    r"\b(itr|income tax return|tax[- ]saving)\b",
    r"\bsip\b.{0,30}\b(returns|calculator|crore)\b",
    r"\b(fd|fixed deposit) (rates?|vs)\b",
    r"\bipo\b.{0,40}\b(should you|worth|apply|gmp|grey market)\b",
)

_NOISE = re.compile("|".join(NOISE_PATTERNS), re.I)

# Word boundaries matter: naive substring matching pairs "stake" with "mistake" and
# "capex" with "capexpo", which is how retail filler slips past the gate.
# re.escape() escapes spaces, so escaping a whole phrase then substituting the space
# produces a pattern that can never match. Escape each word, join on \s+.
_KEYWORDS = re.compile(
    "|".join(
        r"\b" + r"\s+".join(re.escape(word) for word in keyword.split()) + r"\b"
        for keyword in HIGH_IMPACT_KEYWORDS
    ),
    re.I,
)


def _text(item: dict[str, Any]) -> str:
    parts = [
        item.get("headline") or item.get("subject") or "",
        item.get("summary") or item.get("detail") or "",
        item.get("company") or "",
    ]
    return " ".join(p for p in parts if p).lower()


def rule_filter(items: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split items into those worth scoring and those dropped as noise."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for item in items:
        text = _text(item)
        if not text.strip():
            dropped.append(dict(item, dropped_because="empty"))
            continue
        if _NOISE.search(text):
            dropped.append(dict(item, dropped_because="noise pattern"))
            continue
        match = _KEYWORDS.search(text)
        if not match:
            dropped.append(dict(item, dropped_because="no high-impact keyword"))
            continue
        kept.append(dict(item, matched_keyword=match.group().lower()))

    return kept, dropped


def apply_caps(items: Iterable[dict[str, Any]], caps: dict[str, int]) -> dict[str, list[dict[str, Any]]]:
    """Group scored items by category, best first, trimmed to the per-section cap.

    Caps stop one busy category from swamping the briefing. `caps` keys are category
    names; an uncapped category keeps everything.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item.get("category", "uncategorised"), []).append(item)

    out: dict[str, list[dict[str, Any]]] = {}
    for category, group in grouped.items():
        group.sort(key=lambda i: i.get("score", 0), reverse=True)
        limit = caps.get(category)
        out[category] = group[:limit] if limit else group
    return out

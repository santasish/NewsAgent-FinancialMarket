"""Market breadth, sector leadership and institutional derivatives positioning."""

from __future__ import annotations

from typing import Any


def breadth_ratio(breadth: dict[str, Any]) -> dict[str, Any] | None:
    """Advance/decline expressed as a small whole-number ratio, e.g. 1:2."""
    advances = breadth.get("advances")
    declines = breadth.get("declines")
    if not advances or not declines:
        return None

    advances, declines = int(advances), int(declines)

    # Normalise against the smaller side so the ratio stays faithful: 4416/5129 reads
    # as "1:1.2", not the "3:3" that rounding a reduced fraction produces.
    if advances <= declines:
        ratio = f"1:{declines / advances:.1f}"
    else:
        ratio = f"{advances / declines:.1f}:1"

    if advances > declines:
        summary = "buyers held the broader market"
    elif declines > advances * 1.5:
        summary = "sellers dominated well beyond the headline index"
    else:
        summary = "a mixed session under the surface"

    return {
        "advances": advances,
        "declines": declines,
        "unchanged": breadth.get("unchanged"),
        "ratio": ratio,
        "summary": summary,
    }


def rank_sectors(sectors: list[dict[str, Any]], top: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Split sector indices into leaders and laggards by percentage change."""
    ranked = sorted(
        [s for s in sectors if s and s.get("percent_change") is not None],
        key=lambda s: s["percent_change"],
        reverse=True,
    )
    if not ranked:
        return {"outperforming": [], "underperforming": []}

    def shape(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": row["name"],
            "last": row.get("last"),
            "percent_change": row["percent_change"],
        }

    return {
        "outperforming": [shape(r) for r in ranked[:top] if r["percent_change"] > 0],
        "underperforming": [shape(r) for r in reversed(ranked[-top:]) if r["percent_change"] < 0],
    }


def _find(record: dict[str, Any], *needles: str) -> float | None:
    """Locate a column by fuzzy name — NSE's CSV headers drift between revisions."""
    for key, value in record.items():
        normalised = " ".join(str(key).lower().split())
        if all(n in normalised for n in needles):
            return value
    return None


def fii_futures_stance(participant_oi: dict[str, Any]) -> dict[str, Any] | None:
    """FII index-futures long ratio — how foreign desks are positioned on the index."""
    participants = participant_oi.get("participants") or {}
    record = participants.get("FII") or participants.get("FPI")
    if not record:
        return None

    longs = _find(record, "future", "index", "long")
    shorts = _find(record, "future", "index", "short")
    if longs is None or shorts is None or (longs + shorts) == 0:
        return None

    ratio = round(longs / (longs + shorts) * 100, 1)
    if ratio >= 60:
        assessment = "foreign funds are mostly betting on the index rising"
    elif ratio <= 35:
        assessment = "foreign funds are heavily betting on the index falling"
    elif ratio <= 45:
        assessment = "foreign funds lean towards a fall, though less heavily"
    else:
        assessment = "foreign funds are evenly split between a rise and a fall"

    return {
        "as_of": participant_oi.get("date"),
        "long_contracts": longs,
        "short_contracts": shorts,
        "long_ratio_percent": ratio,
        "assessment": assessment,
    }

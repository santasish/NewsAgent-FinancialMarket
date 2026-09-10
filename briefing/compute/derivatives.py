"""Option-chain analytics: PCR, open-interest walls and max pain."""

from __future__ import annotations

from typing import Any

# Conventional read: a low put-call ratio means call writers dominate and the market is
# stretched to the downside; a high one means the reverse.
# Phrased for the reader, not the desk: the payload wording is what the newsletter
# echoes, so it has to be plain English already.
PCR_BANDS = (
    (0.70, "bets on a rise far outnumber bets on a fall; the market is stretched and bounces often start from here"),
    (0.90, "bets on a rise outnumber bets on a fall"),
    (1.10, "bets on a rise and on a fall are roughly balanced"),
    (1.30, "bets on a fall outnumber bets on a rise"),
    (float("inf"), "bets on a fall far outnumber bets on a rise; a sign of complacency about a drop"),
)


def _band(pcr: float) -> str:
    for ceiling, label in PCR_BANDS:
        if pcr < ceiling:
            return label
    return "neutral"


def max_pain(rows: list[dict[str, Any]]) -> float | None:
    """Strike at which the total value of expiring options is smallest.

    For each candidate expiry price, sum what call and put writers would owe; the
    minimum is the level option writers are collectively positioned for.
    """
    strikes = [r["strike"] for r in rows if r.get("strike") is not None]
    if not strikes:
        return None

    best_strike, best_loss = None, None
    for candidate in strikes:
        loss = 0.0
        for row in rows:
            strike = row.get("strike")
            if strike is None:
                continue
            if candidate > strike:
                loss += (row.get("call_oi") or 0) * (candidate - strike)
            elif candidate < strike:
                loss += (row.get("put_oi") or 0) * (strike - candidate)
        if best_loss is None or loss < best_loss:
            best_strike, best_loss = candidate, loss
    return best_strike


def analyse_option_chain(chain: dict[str, Any]) -> dict[str, Any] | None:
    """Derive PCR, OI walls and max pain from a fetched option chain."""
    rows = chain.get("rows") or []
    if not rows:
        return None

    total_call_oi = sum(r.get("call_oi") or 0 for r in rows)
    total_put_oi = sum(r.get("put_oi") or 0 for r in rows)
    if not total_call_oi:
        return None

    pcr = round(total_put_oi / total_call_oi, 2)
    call_wall = max(rows, key=lambda r: r.get("call_oi") or 0)
    put_wall = max(rows, key=lambda r: r.get("put_oi") or 0)

    return {
        "symbol": chain.get("symbol"),
        "expiry": chain.get("expiry"),
        "underlying": chain.get("underlying"),
        "pcr": pcr,
        "pcr_assessment": _band(pcr),
        "call_wall": call_wall.get("strike"),
        "call_wall_oi": call_wall.get("call_oi"),
        "put_wall": put_wall.get("strike"),
        "put_wall_oi": put_wall.get("put_oi"),
        "max_pain": max_pain(rows),
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
    }

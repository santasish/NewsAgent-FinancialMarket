"""Support/resistance levels and moving averages, computed locally.

Everything here is deterministic arithmetic on published OHLC data — no scraped
"analyst levels", and nothing the model has to work out for itself.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Sequence

from briefing.schedule import IST, now_ist

# NSE equity session ends 15:30 IST; the daily bar is only final after that.
MARKET_CLOSE = time(15, 30)


def classic_pivots(high: float, low: float, close: float) -> dict[str, float]:
    """Standard floor-trader pivots from the previous session's range."""
    pivot = (high + low + close) / 3
    span = high - low
    return {
        "pivot": round(pivot, 2),
        "r1": round(2 * pivot - low, 2),
        "r2": round(pivot + span, 2),
        "r3": round(high + 2 * (pivot - low), 2),
        "s1": round(2 * pivot - high, 2),
        "s2": round(pivot - span, 2),
        "s3": round(low - 2 * (high - pivot), 2),
    }


def moving_average(closes: Sequence[float], window: int) -> float | None:
    values = [c for c in closes if c is not None]
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 2)


def drop_incomplete_session(
    rows: Sequence[dict[str, Any]], now: datetime | None = None
) -> list[dict[str, Any]]:
    """Discard a trailing bar for a session that is still in progress.

    Daily feeds publish a partial bar for the running session. Pivots derived from a
    half-formed high/low are simply wrong, so the bar is dropped until the close.
    """
    rows = list(rows)
    if not rows:
        return rows
    moment = now or now_ist()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=IST)
    moment = moment.astimezone(IST)
    if rows[-1].get("date") == moment.date().isoformat() and moment.time() < MARKET_CLOSE:
        return rows[:-1]
    return rows


def compute_levels(
    history: Sequence[dict[str, Any]], now: datetime | None = None
) -> dict[str, Any] | None:
    """Pivots from the last completed session plus 20/50-day moving averages.

    `history` is the daily OHLC list produced by briefing.fetch.macro.
    """
    rows = [r for r in drop_incomplete_session(history, now) if r.get("close") is not None]
    if not rows:
        return None

    previous = rows[-1]
    if None in (previous.get("high"), previous.get("low"), previous.get("close")):
        return None

    closes = [r["close"] for r in rows]
    last_close = closes[-1]
    dma_20 = moving_average(closes, 20)
    dma_50 = moving_average(closes, 50)

    trend = None
    if dma_20 is not None and dma_50 is not None:
        if last_close > dma_20 > dma_50:
            trend = "above both its 20-day and 50-day averages, so the rising trend is intact"
        elif last_close < dma_20 < dma_50:
            trend = "below both its 20-day and 50-day averages, so the falling trend is intact"
        elif last_close > dma_20:
            trend = "above its 20-day average but still below its 50-day average, a mixed picture"
        else:
            trend = "below its 20-day average, a sign of short-term weakness"

    return {
        "reference_session": previous.get("date"),
        "reference_close": round(last_close, 2),
        "reference_high": round(previous["high"], 2),
        "reference_low": round(previous["low"], 2),
        "pivots": classic_pivots(previous["high"], previous["low"], previous["close"]),
        "dma_20": dma_20,
        "dma_50": dma_50,
        "trend": trend,
    }

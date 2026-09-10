"""RSI, short-term price momentum and volume trend — watchlist-only technicals.

Kept separate from briefing.compute.pivots deliberately: the main index sections stay on
classic pivots and 20/50-DMA (see SPEC.md's note on a richer indicator engine that was
built once and reverted at the user's request for reading too much like a trading
desk). These readings were added back at the user's explicit request on 2026-09-10, but
scoped to the user's own watchlist only — the market-wide sections are untouched.
"""

from __future__ import annotations

from typing import Any, Sequence

from briefing.compute.pivots import drop_incomplete_session, moving_average


def rsi(closes: Sequence[float], period: int = 14) -> float | None:
    """Wilder's RSI over the most recent `period` daily changes."""
    values = [c for c in closes if c is not None]
    if len(values) < period + 1:
        return None

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return round(100 - (100 / (1 + relative_strength)), 2)


def rsi_assessment(value: float) -> str:
    """Plain-English zone. Never say "overbought"/"oversold" — house rules ban both."""
    if value >= 70:
        return "stretched to the upside, the kind of reading where a pause or pullback often follows"
    if value <= 30:
        return "stretched to the downside, the kind of reading where a bounce often follows"
    return "in a neutral zone, neither stretched up nor down"


def price_momentum(closes: Sequence[float], period: int = 5) -> dict[str, Any] | None:
    """Percent price change over the last `period` completed sessions."""
    values = [c for c in closes if c is not None]
    if len(values) < period + 1:
        return None
    then, now = values[-period - 1], values[-1]
    if not then:
        return None
    change_percent = round((now - then) / then * 100, 2)
    if change_percent > 0:
        direction = "risen"
    elif change_percent < 0:
        direction = "fallen"
    else:
        direction = "held flat"
    return {"period_days": period, "change_percent": change_percent, "direction": direction}


def volume_trend(rows: Sequence[dict[str, Any]], period: int = 20) -> dict[str, Any] | None:
    """The latest session's volume against its trailing `period`-day average."""
    values = [r for r in rows if r.get("volume") is not None]
    if len(values) < period + 1:
        return None
    latest = values[-1]
    baseline = values[-period - 1 : -1]
    avg_volume = sum(r["volume"] for r in baseline) / len(baseline)
    if not avg_volume:
        return None
    ratio = round(latest["volume"] / avg_volume, 2)
    if ratio >= 1.5:
        assessment = "well above its recent average, a sign of unusually heavy interest"
    elif ratio >= 1.1:
        assessment = "above its recent average"
    elif ratio <= 0.7:
        assessment = "well below its recent average, a sign of thin interest"
    else:
        assessment = "close to its recent average"
    return {
        "latest_volume": int(latest["volume"]),
        "average_volume": int(round(avg_volume)),
        "ratio": ratio,
        "assessment": assessment,
    }


def extra_technicals(history: Sequence[dict[str, Any]], now: Any = None) -> dict[str, Any]:
    """Bundle dma_8, rsi, price_momentum and volume_trend from raw daily OHLCV rows.

    Uses the same "drop an in-progress session's bar" rule as compute_levels, so every
    watchlist reading lines up on the same last-completed-session boundary.
    """
    rows = [r for r in drop_incomplete_session(history, now) if r.get("close") is not None]
    if not rows:
        return {}

    closes = [r["close"] for r in rows]
    out: dict[str, Any] = {}

    dma_8 = moving_average(closes, 8)
    if dma_8 is not None:
        out["dma_8"] = dma_8

    rsi_value = rsi(closes)
    if rsi_value is not None:
        out["rsi"] = rsi_value
        out["rsi_assessment"] = rsi_assessment(rsi_value)

    momentum = price_momentum(closes)
    if momentum:
        out["momentum"] = momentum

    volume = volume_trend(rows)
    if volume:
        out["volume_trend"] = volume

    return out

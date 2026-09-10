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


def contract_snapshot(chain: dict[str, Any], strike: float, option_type: str) -> dict[str, Any] | None:
    """The one row a watchlist entry asked for: its premium, OI and which way OI moved.

    `option_type` is "CE" or "PE". Returns None if the strike isn't in the fetched
    chain or the contract has no trades (no last price) — printing a blank premium
    would violate the zero-fabrication rule just as much as inventing one.
    """
    rows = chain.get("rows") or []
    row = next((r for r in rows if r.get("strike") == strike), None)
    if not row:
        return None

    prefix = "call" if option_type == "CE" else "put"
    premium = row.get(f"{prefix}_ltp")
    if premium is None:
        return None

    underlying = chain.get("underlying")
    # Precomputed so the model states a trader's read (breakeven, how far the underlying
    # has to move) without doing arithmetic itself — that would let it invent a figure
    # the verifier can't check. A call needs the underlying above the breakeven at
    # expiry to be in profit; a put needs it below.
    is_call = option_type == "CE"
    breakeven = round(strike + premium, 2) if is_call else round(strike - premium, 2)
    moneyness = None
    move_to_breakeven_percent = None
    if underlying:
        moneyness = (
            "in the money" if (underlying > strike if is_call else underlying < strike)
            else "out of the money"
        )
        # Signed so the reader can tell direction from the number alone: positive means
        # the underlying still has to move that far (up for a call, down for a put) to
        # reach breakeven; negative means it has already moved past it and the position
        # is sitting in profit by that percentage.
        signed_distance = (breakeven - underlying) if is_call else (underlying - breakeven)
        move_to_breakeven_percent = round(signed_distance / underlying * 100, 2)

    return {
        "symbol": chain.get("symbol"),
        "expiry": chain.get("expiry"),
        "underlying": underlying,
        "strike": strike,
        "option_type": option_type,
        "kind": "call" if option_type == "CE" else "put",
        "premium": premium,
        "open_interest": row.get(f"{prefix}_oi"),
        "oi_change": row.get(f"{prefix}_oi_change"),
        "implied_volatility": row.get(f"{prefix}_iv"),
        "breakeven": breakeven,
        "moneyness": moneyness,
        "move_to_breakeven_percent": move_to_breakeven_percent,
    }

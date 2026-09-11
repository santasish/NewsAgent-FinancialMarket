"""Evening edition payload: today's session, flows, derivatives, after-hours filings."""

from __future__ import annotations

from datetime import date
from typing import Any

from briefing.compute import analyse_option_chain, breadth_ratio, rank_sectors
from briefing.payload.common import (
    SOURCES,
    PayloadContext,
    crore,
    is_after_hours,
    num,
    pct,
    shape_news,
    side,
)


def _index_block(benchmarks: dict[str, Any], name: str) -> dict[str, Any] | None:
    row = benchmarks.get(name)
    if not row:
        return None
    return {
        "close": num(row.get("last")),
        "change": num(row.get("change")),
        "percent_change": pct(row.get("percent_change")),
        "open": num(row.get("open")),
        "high": num(row.get("high")),
        "low": num(row.get("low")),
        "previous_close": num(row.get("previous_close")),
    }


def build_evening_payload(
    ctx: PayloadContext,
    day: date,
    news: list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"date": day.isoformat()}

    indices = ctx.data("nse.indices", "the index closes")
    if indices:
        benchmarks = indices.get("benchmarks", {})
        payload["index_data"] = {
            "nifty_50": _index_block(benchmarks, "NIFTY 50"),
            "bank_nifty": _index_block(benchmarks, "NIFTY BANK"),
            "india_vix": _index_block(benchmarks, "INDIA VIX"),
            "as_of": indices.get("timestamp"),
        }
        breadth = breadth_ratio(indices.get("breadth", {}))
        if breadth:
            payload["market_breadth"] = {
                "advances": f"{breadth['advances']:,}",
                "declines": f"{breadth['declines']:,}",
                "ratio": breadth["ratio"],
                "summary": breadth["summary"],
            }
        sectors = rank_sectors(indices.get("sectors", []))
        payload["sector_performance"] = {
            key: [
                {"name": s["name"], "last": num(s["last"]), "percent_change": pct(s["percent_change"])}
                for s in group
            ]
            for key, group in sectors.items()
            if group
        }

    flows = ctx.data("nse.fii_dii", "foreign and domestic investor flows")
    if flows:
        block = {}
        for label, key in (("FII", "fii"), ("FII/FPI", "fii"), ("DII", "dii")):
            row = flows.get(label)
            if row and key not in block:
                block[key] = {
                    "net_crore": crore(row.get("net_value")),
                    "direction": side(row.get("net_value")),
                    "buy_crore": crore(row.get("buy_value")),
                    "sell_crore": crore(row.get("sell_value")),
                    "date": row.get("date"),
                }
        if block:
            payload["fii_dii_data"] = block

    derivatives: dict[str, Any] = {}
    for symbol, key in (("nifty", "nse.option_chain.nifty"), ("banknifty", "nse.option_chain.banknifty")):
        chain = ctx.data(key, f"{symbol} options data")
        analysis = analyse_option_chain(chain) if chain else None
        if analysis:
            derivatives[symbol] = {
                "expiry": analysis["expiry"],
                "pcr": num(analysis["pcr"]),
                "pcr_assessment": analysis["pcr_assessment"],
                "call_wall_strike": num(analysis["call_wall"], 0),
                "put_wall_strike": num(analysis["put_wall"], 0),
                "max_pain": num(analysis["max_pain"], 0),
            }

    ban = ctx.data("nse.fno_ban", "the list of stocks with frozen derivative trading")
    if ban:
        derivatives["fno_ban"] = ban.get("symbols") or ["None"]
    if derivatives:
        payload["derivatives"] = derivatives

    macro = ctx.data("macro.yfinance", "oil, bond and currency readings")
    if macro:
        quotes = macro.get("quotes", {})
        payload["macro_data"] = {
            name: {"last": num(q.get("last")), "percent_change": pct(q.get("percent_change"))}
            for name, q in quotes.items()
            if name in ("brent_crude", "us_10y_yield", "usd_inr", "dxy")
        }
        payload["global_snapshot"] = {
            name: {"last": num(q.get("last")), "percent_change": pct(q.get("percent_change"))}
            for name, q in quotes.items()
            if name in ("sp500", "nasdaq", "dow", "ftse", "dax")
        }

    intraday = [shape_news(i) for i in news if not is_after_hours(i, day)]
    after_hours = [shape_news(i) for i in news if is_after_hours(i, day)]
    if intraday:
        payload["filtered_news"] = intraday
    if after_hours:
        payload["after_hours_filings"] = after_hours

    payload["sources"] = [SOURCES["nse_daily"], SOURCES["bse_filings"]]
    return ctx.finish(payload)

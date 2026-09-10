"""Morning edition payload: overnight global cues, positioning and today's game plan."""

from __future__ import annotations

from datetime import date
from typing import Any

from briefing.compute import (
    analyse_option_chain,
    compute_levels,
    fii_futures_stance,
    rank_sectors,
)
from briefing.payload.common import SOURCES, PayloadContext, levels_block, num, pct, shape_news, watchlist_block

GLOBAL_SYMBOLS = ("sp500", "nasdaq", "dow", "nikkei", "hang_seng", "ftse", "dax")
MACRO_SYMBOLS = ("brent_crude", "us_10y_yield", "dxy", "usd_inr")

CATEGORY_SECTIONS = {
    "macro": "key_catalysts",
    "global": "key_catalysts",
    "mna": "special_situations",
    "earnings": "earnings",
    "microcap": "microcap_catalysts",
    "pib": "pib_releases",
}


def _quote_block(quotes: dict[str, Any], names) -> dict[str, Any]:
    return {
        name: {
            "last": num(quotes[name].get("last")),
            "change": num(quotes[name].get("change")),
            "percent_change": pct(quotes[name].get("percent_change")),
        }
        for name in names
        if name in quotes and quotes[name].get("last") is not None
    }


def build_morning_payload(
    ctx: PayloadContext,
    day: date,
    news: list[dict[str, Any]],
    watchlist: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"date": day.isoformat()}

    macro = ctx.data("macro.yfinance", "global markets")
    if macro:
        quotes = macro.get("quotes", {})
        payload["global_cues"] = _quote_block(quotes, GLOBAL_SYMBOLS)
        payload["macro_indicators"] = _quote_block(quotes, MACRO_SYMBOLS)

        pivots: dict[str, Any] = {}
        for name in ("nifty_50", "bank_nifty"):
            levels = compute_levels(macro.get("history", {}).get(name, []))
            if levels:
                pivots[name] = levels_block(levels)
        if pivots:
            payload["key_technical_pivots"] = pivots

    gift = ctx.data("gift_nifty.scrape", "the pre-market indicator")
    if gift:
        payload["gift_nifty"] = {
            "level": num(gift.get("level")),
            "change": num(gift.get("change")),
            "percent_change": pct(gift.get("percent_change")),
        }

    positioning: dict[str, Any] = {}
    participants = ctx.data("nse.participant_oi", "foreign funds' futures stance")
    stance = fii_futures_stance(participants) if participants else None
    if stance:
        positioning["fii_index_futures"] = {
            "as_of": stance["as_of"],
            "long_ratio_percent": f"{stance['long_ratio_percent']:.1f}%",
            "assessment": stance["assessment"],
        }

    chain = ctx.data("nse.option_chain.nifty", "Nifty options data")
    analysis = analyse_option_chain(chain) if chain else None
    if analysis:
        positioning["nifty_option_chain"] = {
            "expiry": analysis["expiry"],
            "call_wall_strike": num(analysis["call_wall"], 0),
            "put_wall_strike": num(analysis["put_wall"], 0),
            "pcr": num(analysis["pcr"]),
            "pcr_assessment": analysis["pcr_assessment"],
            "max_pain": num(analysis["max_pain"], 0),
        }

    ban = ctx.data("nse.fno_ban", "the list of stocks with frozen derivative trading")
    if ban:
        positioning["fno_ban_today"] = ban.get("symbols") or ["None"]
    if positioning:
        payload["fii_dii_derivatives"] = positioning

    indices = ctx.data("nse.indices", "sector moves")
    if indices:
        sectors = rank_sectors(indices.get("sectors", []))
        payload["sector_performance"] = {
            key: [
                {"name": s["name"], "last": num(s["last"]), "percent_change": pct(s["percent_change"])}
                for s in group
            ]
            for key, group in sectors.items()
            if group
        }

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in news:
        if item.get("source") == "PIB":
            section = "pib_releases"
        else:
            section = CATEGORY_SECTIONS.get(item.get("category"), "key_catalysts")
        grouped.setdefault(section, []).append(shape_news(item))
    payload.update(grouped)

    if watchlist:
        shaped_watchlist = watchlist_block(watchlist, day)
        if shaped_watchlist:
            payload["watchlist"] = shaped_watchlist

    payload["sources"] = [SOURCES["pib"], SOURCES["nse_filings"], SOURCES["us_treasury"]]
    return ctx.finish(payload)

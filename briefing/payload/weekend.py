"""Weekend and NSE-holiday payloads.

No live session means no pivots, no intraday levels and no overnight positions. Both
editions lean on global markets, macro, and whatever was filed while India was shut.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from briefing.payload.common import SOURCES, PayloadContext, num, pct, shape_news
from briefing.schedule import is_trading_day

GLOBAL_SYMBOLS = ("sp500", "nasdaq", "dow", "ftse", "dax", "nikkei", "hang_seng")
MACRO_SYMBOLS = ("brent_crude", "us_10y_yield", "dxy", "usd_inr")

CATEGORY_SECTIONS = {
    "mna": "special_situations",
    "earnings": "special_situations",
    "microcap": "special_situations",
    "pib": "pib_releases",
}


def next_trading_day(day: date) -> date:
    candidate = day + timedelta(days=1)
    for _ in range(14):
        if is_trading_day(candidate):
            return candidate
        candidate += timedelta(days=1)
    return candidate


def _quotes(macro: dict[str, Any], names) -> dict[str, Any]:
    quotes = macro.get("quotes", {})
    return {
        name: {
            "last": num(quotes[name].get("last")),
            "percent_change": pct(quotes[name].get("percent_change")),
            "as_of": quotes[name].get("as_of"),
        }
        for name in names
        if name in quotes and quotes[name].get("last") is not None
    }


def _base(ctx: PayloadContext, day: date, news: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "date": day.isoformat(),
        "next_session": next_trading_day(day).isoformat(),
    }
    macro = ctx.data("macro.yfinance", "global markets")
    if macro:
        payload["global_cues"] = _quotes(macro, GLOBAL_SYMBOLS)
        payload["macro_indicators"] = _quotes(macro, MACRO_SYMBOLS)
    return payload


def build_weekend_morning_payload(
    ctx: PayloadContext, day: date, news: list[dict[str, Any]]
) -> dict[str, Any]:
    payload = _base(ctx, day, news)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in news:
        if item.get("source") == "PIB":
            section = "pib_releases"
        else:
            section = CATEGORY_SECTIONS.get(item.get("category"), "news_catalysts")
        grouped.setdefault(section, []).append(shape_news(item))
    payload.update(grouped)

    payload["sources"] = [SOURCES["pib"], SOURCES["nse_filings"]]
    return ctx.finish(payload)


def build_weekend_evening_payload(
    ctx: PayloadContext, day: date, news: list[dict[str, Any]]
) -> dict[str, Any]:
    payload = _base(ctx, day, news)

    macro = ctx.data("macro.yfinance", "global wrap")
    if macro:
        payload["global_wrap"] = payload.pop("global_cues", None)

    if news:
        payload["news_catalysts"] = [shape_news(i) for i in news]

    payload["sources"] = [SOURCES["nse_daily"], SOURCES["rbi"]]
    return ctx.finish(payload)

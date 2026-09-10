"""Runs every fetcher and reports what came back.

Fetchers never raise: each returns a FetchResult, and the caller decides which sections
of the briefing have to be omitted.
"""

from __future__ import annotations

from typing import Any

from briefing.config import Config
from briefing.fetch import macro as macro_fetch
from briefing.fetch import bse, gift_nifty, news, nse, pib
from briefing.fetch.base import FetchResult


def fetch_all(config: Config, *, include_news: bool = True) -> list[FetchResult]:
    session = nse.NSESession()
    results: list[FetchResult] = [
        macro_fetch.fetch_macro(),
        nse.fetch_indices(session),
        nse.fetch_fii_dii(session),
        nse.fetch_option_chain(session, "NIFTY"),
        nse.fetch_option_chain(session, "BANKNIFTY"),
        nse.fetch_fno_ban(session),
        nse.fetch_participant_oi(session),
        nse.fetch_corporate_announcements(session),
        nse.fetch_block_deals(session),
        bse.fetch_announcements(),
        pib.fetch_pib(),
        gift_nifty.fetch_gift_nifty(),
    ]
    if include_news:
        results.append(
            news.fetch_news(
                domains=config.get("news_domains"),
                queries=config.get("news_queries", None),
            )
        )
    return results


def preview(result: FetchResult) -> str:
    """One-line human summary of what a fetcher returned."""
    if not result.ok:
        return (result.error or "unknown error")[:110]

    data: Any = result.data
    if isinstance(data, list):
        head = data[0] if data else None
        label = ""
        if isinstance(head, dict):
            label = str(
                head.get("headline") or head.get("subject") or head.get("symbol") or ""
            )[:60]
        return f"{len(data)} items  {label}"

    if not isinstance(data, dict):
        return str(data)[:110]

    if "quotes" in data:
        quotes = data["quotes"]
        bits = [
            f"{k}={quotes[k]['last']}" for k in ("brent_crude", "us_10y_yield", "usd_inr") if k in quotes
        ]
        return f"{len(quotes)} symbols  " + "  ".join(bits)
    if "benchmarks" in data:
        bits = [f"{k}={v['last']} ({v['percent_change']}%)" for k, v in data["benchmarks"].items()]
        return "  ".join(bits)
    if "participants" in data:
        return f"{data['date']}  rows={list(data['participants'])}"
    if "rows" in data:
        return f"{data['symbol']} {data['expiry']}  underlying={data['underlying']}  strikes={len(data['rows'])}"
    if "symbols" in data:
        symbols = data["symbols"]
        return f"{len(symbols)} banned  {', '.join(symbols[:5])}"
    if "level" in data:
        return f"level={data['level']}  change={data.get('change')}"
    if {"FII", "DII"} & set(data):
        return "  ".join(f"{k} net={v['net_value']}" for k, v in data.items())
    return str(data)[:110]

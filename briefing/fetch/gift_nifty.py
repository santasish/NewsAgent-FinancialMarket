"""GIFT Nifty pre-market indicator.

There is no free API for this. NSE IX (the exchange that lists it) gates its quote API,
and Moneycontrol's `gift-nifty-50` URL actually renders NIFTY 50 spot — a number that
looks right and is wrong.

So this fetcher FAILS CLOSED: it returns a level only when the page markup positively
identifies the instrument as GIFT Nifty. A wrong number in a trade plan is far worse
than a missing line, and the morning briefing already infers the implied open from
overnight US and Asian moves when this is absent.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from briefing.fetch.base import DEFAULT_TIMEOUT, USER_AGENT, FetchResult, with_retries

PAGE = "https://www.moneycontrol.com/indian-indices/gift-nifty-50-9.html"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_PRICE = re.compile(r"\b(\d{2},\d{3}(?:\.\d{1,2})?)\b")
_CHANGE = re.compile(r"([+-]?\d+(?:\.\d{1,2})?)\s*\(\s*([+-]?\d+\.\d{1,2})\s*%\s*\)")
_IS_GIFT = re.compile(r"gift[\s-]*nifty", re.I)


def _instrument_label(soup: Any, price_node: Any) -> str:
    """Whatever the page claims THIS price belongs to.

    Scoped to the price widget's own ancestors — a page-level search picks up unrelated
    navigation and would let a mislabelled quote through.
    """
    node = price_node
    for _ in range(6):
        if node is None:
            break
        labelled = node.select_one("[data-name]") if hasattr(node, "select_one") else None
        if labelled and labelled.get("data-name"):
            return str(labelled["data-name"])
        node = node.parent
    heading = soup.select_one("h1")
    return heading.get_text(" ", strip=True) if heading else ""


def fetch_gift_nifty(timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    def run() -> dict[str, Any]:
        from bs4 import BeautifulSoup

        response = requests.get(PAGE, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        node = soup.select_one("#sp_val")
        if node is None:
            raise ValueError("no quote node on the page")

        label = _instrument_label(soup, node)
        if not _IS_GIFT.search(label):
            raise ValueError(
                f"page quotes {label or 'an unidentified instrument'}, not GIFT Nifty — "
                "refusing to report it as GIFT Nifty"
            )

        match = _PRICE.search(node.get_text(" ", strip=True))
        if not match:
            raise ValueError("no price found in the GIFT Nifty quote node")

        change_node = soup.select_one("#sp_ch_prch")
        change = _CHANGE.search(change_node.get_text(" ", strip=True)) if change_node else None

        return {
            "instrument": label,
            "level": float(match.group(1).replace(",", "")),
            "change": float(change.group(1)) if change else None,
            "percent_change": float(change.group(2)) if change else None,
            "source_url": PAGE,
        }

    return with_retries("gift_nifty.scrape", run, attempts=2)

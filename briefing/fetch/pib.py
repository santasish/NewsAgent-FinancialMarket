"""Press Information Bureau releases — the official government/ministry source.

PIB's RSS feed (RssMain.aspx) ignores its own Lang parameter and serves Hindi only, so
the English release listing is scraped instead. Each release carries the PRID that the
briefing cites as its "PIB Release ID".
"""

from __future__ import annotations

import re
from typing import Any

import requests

from briefing.fetch.base import DEFAULT_TIMEOUT, USER_AGENT, FetchResult, with_retries

LISTING = "https://www.pib.gov.in/Allrel.aspx?reg=3&lang=1"
RELEASE_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID={prid}"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_PRID = re.compile(r"PRID=(\d+)")
_MIN_ENGLISH_RATIO = 0.8


def _is_english(text: str) -> bool:
    if not text:
        return False
    return sum(c.isascii() for c in text) / len(text) >= _MIN_ENGLISH_RATIO


def fetch_pib(url: str = LISTING, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    def run() -> list[dict[str, Any]]:
        from bs4 import BeautifulSoup

        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for anchor in soup.select("a[href*='PRID=']"):
            match = _PRID.search(anchor["href"])
            headline = anchor.get_text(" ", strip=True)
            if not match or not headline or not _is_english(headline):
                continue
            prid = match.group(1)
            if prid in seen:
                continue
            seen.add(prid)
            out.append(
                {
                    "headline": re.sub(r"\s+", " ", headline),
                    "release_id": prid,
                    "url": RELEASE_URL.format(prid=prid),
                    "source": "PIB",
                }
            )

        if not out:
            raise ValueError("no English PIB releases found on the listing page")
        return out

    return with_retries("pib.releases", run)

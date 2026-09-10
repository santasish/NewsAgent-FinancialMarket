"""Headlines via Google News RSS, restricted to the approved publisher list.

Queries are site-scoped so the noise gate has less to reject; whatever survives still
goes through the rule filter and the LLM relevancy scorer downstream.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any

from briefing.fetch.base import DEFAULT_TIMEOUT, USER_AGENT, FetchResult, with_retries

RSS = "https://news.google.com/rss/search"
LOCALE = {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"}

DEFAULT_QUERIES = {
    "earnings": '"Q1 results" OR "Q2 results" OR "Q3 results" OR "Q4 results" OR concall OR "earnings call" OR guidance',
    "special_situations": 'buyback OR demerger OR merger OR "stake sale" OR "open offer" OR amalgamation',
    "microcap": '"order win" OR "bags order" OR "bulk deal" OR "block deal" OR "capacity expansion" OR "letter of intent"',
    "macro_policy": "RBI OR repo OR inflation OR GDP OR SEBI OR fiscal OR rupee",
    "flows": "FII OR DII OR \"foreign investors\" OR \"institutional flows\"",
    "market_moves": "Nifty OR Sensex OR \"Bank Nifty\" OR \"crude oil\"",
}

_TAGS = re.compile(r"<[^>]+>")

# Google News redirect URLs run to ~800 characters and are never printed in the
# briefing; carrying them into the payload is pure token cost.
_REDIRECT = re.compile(r"^https?://news\.google\.com/")


def _clean(text: str) -> str:
    """Unescape entities and normalise whitespace.

    Feedparser hands back HTML-escaped titles; left alone they reach the briefing as
    `Jewellers&rsquo;` or, worse, mojibake.
    """
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", text))).strip()


def build_query(keywords: str, domains: list[str], window: str = "1d") -> str:
    sites = " OR ".join(f"site:{d}" for d in domains)
    return f"({sites}) ({keywords}) when:{window}"


def fetch_news(
    domains: list[str],
    queries: dict[str, str] | None = None,
    window: str = "1d",
) -> FetchResult:
    def run() -> list[dict[str, Any]]:
        import feedparser
        import requests

        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for topic, keywords in (queries or DEFAULT_QUERIES).items():
            params = dict(LOCALE, q=build_query(keywords, domains, window))
            url = f"{RSS}?{urllib.parse.urlencode(params)}"
            # Fetch the bytes ourselves so feedparser honours the declared XML encoding;
            # letting it fetch produces mojibake on non-ASCII punctuation.
            response = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.content)

            for entry in parsed.entries:
                headline = _clean(entry.get("title", ""))
                key = re.sub(r"\W+", "", headline.lower())[:80]
                if not headline or key in seen:
                    continue
                seen.add(key)

                summary = _clean(entry.get("summary", ""))[:400]
                # Google News summaries are just the headline plus the publisher name.
                if summary and headline[:60].lower() in summary.lower():
                    summary = ""

                link = entry.get("link") or ""
                out.append(
                    {
                        "headline": headline,
                        "summary": summary or None,
                        "url": None if _REDIRECT.match(link) else link,
                        "published": entry.get("published"),
                        "publisher": (entry.get("source") or {}).get("title", ""),
                        "topic": topic,
                        "source": "GoogleNews",
                    }
                )
        if not out:
            raise ValueError("no headlines returned across all queries")
        return out

    return with_retries("news.google_rss", run, attempts=2)

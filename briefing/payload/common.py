"""Shared payload machinery.

Design rule (see SPEC.md): the payload pre-computes and pre-formats every value the
briefing will print. The model copies numbers, it never derives them. That is what lets
the verifier reject any figure it cannot trace back here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from email.utils import parsedate_to_datetime
from typing import Any, Iterable

from briefing.fetch.base import FetchResult
from briefing.schedule import IST

MARKET_CLOSE = time(15, 30)

# Sources that fail more often than they work from outside India (BSE) or have no free
# feed at all (GIFT Nifty). Their absence is the normal state, not an outage, so it
# must not put a "missing data" note at the top of every issue.
OPTIONAL_SOURCES = frozenset({"bse.announcements", "gift_nifty.scrape"})

SOURCES = {
    "nse_daily": {
        "name": "NSE Provisional Equity Reports",
        "label": "NSE Daily Market Activity",
        "url": "https://www.nseindia.com/market-data/daily-reports",
    },
    "nse_filings": {
        "name": "NSE Corporate Announcements",
        "label": "NSE India Corporate Filings",
        "url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    },
    "bse_filings": {
        "name": "BSE Corporate Filing Announcements",
        "label": "BSE Corporate Disclosures",
        "url": "https://www.bseindia.com/corporates/ann.html",
    },
    "pib": {
        "name": "Press Information Bureau (PIB India)",
        "label": "PIB Press Releases Portal",
        "url": "https://www.pib.gov.in",
    },
    "rbi": {
        "name": "Reserve Bank of India",
        "label": "RBI Official Releases",
        "url": "https://www.rbi.org.in/",
    },
    "us_treasury": {
        "name": "US Department of the Treasury",
        "label": "US Treasury Rates Portal",
        "url": "https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics",
    },
}


def num(value: Any, decimals: int = 2) -> str | None:
    """Format a number exactly as it should appear in the briefing."""
    if value is None:
        return None
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return None


def pct(value: Any, decimals: int = 2) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):+.{decimals}f}%"
    except (TypeError, ValueError):
        return None


def crore(value: Any) -> str | None:
    """Rupee crore amounts, printed as a magnitude — direction is stated in words."""
    if value is None:
        return None
    try:
        return f"{abs(float(value)):,.2f}"
    except (TypeError, ValueError):
        return None


def side(value: Any, positive: str = "BUYers", negative: str = "SELLers") -> str | None:
    if value is None:
        return None
    try:
        return positive if float(value) >= 0 else negative
    except (TypeError, ValueError):
        return None


def to_ist(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    try:
        return parsedate_to_datetime(text).astimezone(IST)
    except (TypeError, ValueError):
        pass
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def is_after_hours(item: dict[str, Any], day: date) -> bool:
    """True when an item was filed after today's close.

    The date check matters: without it, anything published at 21:00 last night is
    misfiled as tonight's after-hours disclosure.
    """
    moment = to_ist(item.get("published") or item.get("time"))
    return bool(moment and moment.date() == day and moment.time() >= MARKET_CLOSE)


def shape_news(item: dict[str, Any]) -> dict[str, Any]:
    """Trim a scored item down to what the generator needs."""
    moment = to_ist(item.get("published") or item.get("time"))
    shaped = {
        "headline": item.get("headline") or item.get("subject"),
        "summary": (item.get("summary") or item.get("detail") or "").strip() or None,
        "company": item.get("company"),
        "category": item.get("category"),
        "score": item.get("score"),
        "source": item.get("source"),
        "url": item.get("url"),
    }
    if moment:
        shaped["time"] = moment.strftime("%H:%M IST")
    return {k: v for k, v in shaped.items() if v is not None}


@dataclass
class PayloadContext:
    """Carries fetch results and records which sections had to be dropped."""

    results: dict[str, FetchResult]
    missing: list[str] = field(default_factory=list)

    @classmethod
    def from_results(cls, results: Iterable[FetchResult]) -> "PayloadContext":
        return cls(results={r.name: r for r in results})

    def data(self, source_name: str, section: str) -> Any | None:
        result = self.results.get(source_name)
        if result is not None and result.ok:
            return result.data
        if source_name not in OPTIONAL_SOURCES and section not in self.missing:
            self.missing.append(section)
        return None

    def finish(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Drop empty sections so the prompt's omit-silently rule has nothing to print."""
        cleaned = {key: value for key, value in payload.items() if value or value == 0}
        cleaned["degraded"] = bool(self.missing)
        cleaned["missing_sections"] = self.missing
        return cleaned

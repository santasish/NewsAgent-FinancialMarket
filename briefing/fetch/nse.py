"""NSE fetchers.

NSE's JSON endpoints are unofficial and gated behind an anti-bot layer: a bare request
to any /api/ path returns 403. A session must first load a market-data page to collect
cookies, and the API call must then look like an XHR from that page. Cookies expire, so
`get_json` re-warms once on a 401/403 before giving up.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from typing import Any

import requests

from briefing.fetch.base import DEFAULT_TIMEOUT, USER_AGENT, FetchResult, with_retries

BASE = "https://www.nseindia.com"
ARCHIVES = "https://nsearchives.nseindia.com"

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

XHR_HEADERS = {
    "Accept": "*/*",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
}

WARMUP_PAGES = (
    f"{BASE}/market-data/live-equity-market",
    f"{BASE}/option-chain",
)

BENCHMARKS = ("NIFTY 50", "NIFTY BANK", "INDIA VIX")

SECTOR_INDICES = (
    "NIFTY IT",
    "NIFTY BANK",
    "NIFTY METAL",
    "NIFTY AUTO",
    "NIFTY REALTY",
    "NIFTY PHARMA",
    "NIFTY FMCG",
    "NIFTY ENERGY",
    "NIFTY FIN SERVICE",
    "NIFTY MEDIA",
    "NIFTY PSU BANK",
    "NIFTY CONSUMER DURABLES",
)


class NSESession:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self._warm = False

    def warm(self) -> None:
        for page in WARMUP_PAGES:
            self.session.get(page, timeout=self.timeout)
        self._warm = True

    def _request(self, url: str, referer: str) -> requests.Response:
        if not self._warm:
            self.warm()
        headers = dict(XHR_HEADERS, Referer=referer)
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        if response.status_code in (401, 403):
            self.warm()
            response = self.session.get(url, headers=headers, timeout=self.timeout)
        return response

    def get_json(self, path: str, referer: str = f"{BASE}/market-data/live-equity-market") -> Any:
        response = self._request(f"{BASE}{path}", referer)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, referer: str = f"{BASE}/") -> str:
        response = self._request(url, referer)
        response.raise_for_status()
        return response.text


def _num(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def fetch_indices(session: NSESession) -> FetchResult:
    """Benchmarks, sector indices and market breadth in one call."""

    def run() -> dict[str, Any]:
        raw = session.get_json("/api/allIndices")
        rows = {row["index"]: row for row in raw.get("data", [])}

        def shape(name: str) -> dict[str, Any] | None:
            row = rows.get(name)
            if not row:
                return None
            return {
                "name": name,
                "last": _num(row.get("last")),
                "open": _num(row.get("open")),
                "high": _num(row.get("high")),
                "low": _num(row.get("low")),
                "previous_close": _num(row.get("previousClose")),
                "change": _num(row.get("variation")),
                "percent_change": _num(row.get("percentChange")),
                "advances": _num(row.get("advances")),
                "declines": _num(row.get("declines")),
            }

        return {
            "timestamp": raw.get("timestamp"),
            "benchmarks": {n: shape(n) for n in BENCHMARKS if shape(n)},
            "sectors": [shape(n) for n in SECTOR_INDICES if shape(n)],
            "breadth": {
                "advances": _num(raw.get("advances")),
                "declines": _num(raw.get("declines")),
                "unchanged": _num(raw.get("unchanged")),
            },
        }

    return with_retries("nse.indices", run)


def fetch_fii_dii(session: NSESession) -> FetchResult:
    def run() -> dict[str, Any]:
        raw = session.get_json("/api/fiidiiTradeReact")
        out: dict[str, Any] = {}
        for row in raw:
            key = row.get("category", "").strip().upper()
            out[key] = {
                "date": row.get("date"),
                "buy_value": _num(row.get("buyValue")),
                "sell_value": _num(row.get("sellValue")),
                "net_value": _num(row.get("netValue")),
            }
        if not out:
            raise ValueError("no FII/DII rows returned")
        return out

    return with_retries("nse.fii_dii", run)


def fetch_option_chain(session: NSESession, symbol: str = "NIFTY") -> FetchResult:
    """Nearest-expiry option chain rows. PCR / OI walls are derived in briefing.compute."""

    def run() -> dict[str, Any]:
        referer = f"{BASE}/option-chain"
        info = session.get_json(
            f"/api/option-chain-contract-info?symbol={symbol}", referer=referer
        )
        expiries = info.get("expiryDates") or []
        if not expiries:
            raise ValueError(f"no expiry dates for {symbol}")
        expiry = expiries[0]
        raw = session.get_json(
            f"/api/option-chain-v3?type=Indices&symbol={symbol}&expiry={expiry}",
            referer=referer,
        )
        records = raw.get("records") or {}
        rows = records.get("data") or []
        if not rows:
            raise ValueError(f"empty option chain for {symbol} {expiry}")
        return {
            "symbol": symbol,
            "expiry": expiry,
            "underlying": _num(records.get("underlyingValue")),
            "timestamp": records.get("timestamp"),
            "rows": [
                {
                    "strike": _num(row.get("strikePrice")),
                    "call_oi": _num((row.get("CE") or {}).get("openInterest")),
                    "call_oi_change": _num((row.get("CE") or {}).get("changeinOpenInterest")),
                    "put_oi": _num((row.get("PE") or {}).get("openInterest")),
                    "put_oi_change": _num((row.get("PE") or {}).get("changeinOpenInterest")),
                }
                for row in rows
            ],
        }

    return with_retries(f"nse.option_chain.{symbol.lower()}", run)


def _announcement(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol"),
        "company": row.get("sm_name") or row.get("comp"),
        "subject": (row.get("desc") or row.get("subject") or "").strip(),
        "detail": (row.get("attchmntText") or "").strip()[:600],
        "time": row.get("an_dt") or row.get("sort_date"),
        "url": row.get("attchmntFile"),
        "source": "NSE",
    }


def fetch_corporate_announcements(session: NSESession) -> FetchResult:
    def run() -> list[dict[str, Any]]:
        raw = session.get_json("/api/corporate-announcements?index=equities")
        return [_announcement(row) for row in raw if isinstance(row, dict)]

    return with_retries("nse.announcements", run)


def fetch_block_deals(session: NSESession) -> FetchResult:
    def run() -> list[dict[str, Any]]:
        raw = session.get_json("/api/block-deal")
        return [
            {
                "symbol": row.get("symbol"),
                "company": row.get("name"),
                "client": row.get("clientName"),
                "buy_sell": row.get("buySell"),
                "quantity": _num(row.get("quantityTraded")),
                "price": _num(row.get("tradePrice")),
            }
            for row in (raw.get("data") or [])
        ]

    return with_retries("nse.block_deals", run)


def fetch_fno_ban(session: NSESession) -> FetchResult:
    """Securities banned from F&O trading for the current session."""

    def run() -> dict[str, Any]:
        text = session.get_text(f"{ARCHIVES}/content/fo/fo_secban.csv")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise ValueError("empty secban file")
        header = lines[0]
        symbols = []
        for line in lines[1:]:
            parts = line.split(",", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                symbols.append(parts[1].strip())
        return {"header": header, "symbols": symbols}

    return with_retries("nse.fno_ban", run)


def fetch_participant_oi(session: NSESession, day: date | None = None) -> FetchResult:
    """Participant-wise open interest (FII/DII/Client/Pro index futures positioning).

    Published after the close, so the file for `day` may not exist yet; walk back up to
    five calendar days to find the most recent one.
    """

    def run() -> dict[str, Any]:
        start = day or date.today()
        last_error: Exception | None = None
        for back in range(6):
            stamp = (start - timedelta(days=back)).strftime("%d%m%Y")
            url = f"{ARCHIVES}/content/nsccl/fao_participant_oi_{stamp}.csv"
            try:
                text = session.get_text(url)
            except Exception as exc:
                last_error = exc
                continue
            rows = list(csv.reader(io.StringIO(text)))
            header_idx = next(
                (i for i, r in enumerate(rows) if r and r[0].strip() == "Client Type"), None
            )
            if header_idx is None:
                continue
            header = [c.strip() for c in rows[header_idx]]
            out = {}
            for row in rows[header_idx + 1 :]:
                if not row or not row[0].strip():
                    continue
                record = dict(zip(header, [c.strip() for c in row]))
                out[record["Client Type"]] = {
                    k: _num(v) for k, v in record.items() if k != "Client Type"
                }
            if out:
                return {"date": stamp, "participants": out}
        raise ValueError(f"no participant OI file found ({last_error})")

    return with_retries("nse.participant_oi", run)


def fetch_holidays(session: NSESession) -> FetchResult:
    def run() -> list[str]:
        raw = session.get_json("/api/holiday-master?type=trading")
        segment = raw.get("CM") or next(iter(raw.values()), [])
        days = []
        for row in segment:
            raw_date = row.get("tradingDate")
            if not raw_date:
                continue
            from datetime import datetime as _dt

            days.append(_dt.strptime(raw_date, "%d-%b-%Y").date().isoformat())
        if not days:
            raise ValueError("no holidays parsed")
        return sorted(days)

    return with_retries("nse.holidays", run)

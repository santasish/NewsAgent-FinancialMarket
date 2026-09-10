"""OHLC history for whatever symbols are on the user's day-to-day watchlist.

Same yfinance approach as briefing.fetch.macro, but for an arbitrary, run-time list of
NSE symbols rather than the fixed index/macro set.
"""

from __future__ import annotations

import warnings
from typing import Any

from briefing.fetch.base import FetchResult, with_retries

HISTORY_DAYS = 90


def _clean(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else round(result, 4)  # NaN check


def _rows(series: Any) -> list[dict[str, Any]]:
    tail = series.tail(HISTORY_DAYS)
    return [
        {
            "date": str(index.date()),
            "open": _clean(row["Open"]),
            "high": _clean(row["High"]),
            "low": _clean(row["Low"]),
            "close": _clean(row["Close"]),
        }
        for index, row in tail.iterrows()
    ]


def fetch_watchlist_quotes(symbols: list[str]) -> FetchResult:
    """Daily OHLC history per symbol, keyed by the plain symbol (not the .NS ticker)."""

    def run() -> dict[str, Any]:
        import yfinance as yf

        tickers = {symbol: f"{symbol}.NS" for symbol in symbols}

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            frame = yf.download(
                list(tickers.values()),
                period="6mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=True,
            )

        if frame is None or frame.empty:
            raise ValueError("yfinance returned no data")

        out: dict[str, Any] = {}
        if len(tickers) == 1:
            # yfinance drops the per-ticker grouping when only one symbol is requested.
            symbol = next(iter(tickers))
            series = frame.dropna(subset=["Close"])
            if not series.empty:
                out[symbol] = _rows(series)
        else:
            for symbol, ticker in tickers.items():
                try:
                    series = frame[ticker].dropna(subset=["Close"])
                except KeyError:
                    continue
                if not series.empty:
                    out[symbol] = _rows(series)

        if not out:
            raise ValueError("no watchlist symbols resolved from yfinance")
        return out

    return with_retries("watchlist.yfinance", run, attempts=2)

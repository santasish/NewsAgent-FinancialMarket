"""Global macro and index data via yfinance.

One batched download covers every symbol. History is kept only for the symbols that
feed pivot and moving-average calculations, to keep the payload small.
"""

from __future__ import annotations

import warnings
from typing import Any

from briefing.fetch.base import FetchResult, with_retries

TICKERS = {
    "brent_crude": "BZ=F",
    "us_10y_yield": "^TNX",
    "dxy": "DX-Y.NYB",
    "usd_inr": "INR=X",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "nikkei": "^N225",
    "hang_seng": "^HSI",
    "ftse": "^FTSE",
    "dax": "^GDAXI",
    "nifty_50": "^NSEI",
    "bank_nifty": "^NSEBANK",
}

HISTORY_FOR = ("nifty_50", "bank_nifty")
HISTORY_DAYS = 90


def _clean(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else round(result, 4)  # NaN check


def fetch_macro(history_for: tuple[str, ...] = HISTORY_FOR) -> FetchResult:
    def run() -> dict[str, Any]:
        import yfinance as yf

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            frame = yf.download(
                list(TICKERS.values()),
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

        quotes: dict[str, Any] = {}
        history: dict[str, Any] = {}

        for name, symbol in TICKERS.items():
            try:
                series = frame[symbol].dropna(subset=["Close"])
            except KeyError:
                continue
            if series.empty:
                continue

            closes = series["Close"]
            last = _clean(closes.iloc[-1])
            previous = _clean(closes.iloc[-2]) if len(closes) > 1 else None
            change = round(last - previous, 4) if last is not None and previous else None
            quotes[name] = {
                "symbol": symbol,
                "last": last,
                "previous_close": previous,
                "change": change,
                "percent_change": (
                    round(change / previous * 100, 2) if change is not None and previous else None
                ),
                "as_of": str(series.index[-1].date()),
            }

            if name in history_for:
                tail = series.tail(HISTORY_DAYS)
                history[name] = [
                    {
                        "date": str(index.date()),
                        "open": _clean(row["Open"]),
                        "high": _clean(row["High"]),
                        "low": _clean(row["Low"]),
                        "close": _clean(row["Close"]),
                    }
                    for index, row in tail.iterrows()
                ]

        if not quotes:
            raise ValueError("no symbols resolved from yfinance response")
        return {"quotes": quotes, "history": history}

    return with_retries("macro.yfinance", run, attempts=2)

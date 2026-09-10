from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

IST = timezone(timedelta(hours=5, minutes=30))

EDITIONS = ("morning", "evening")

_HOLIDAYS_FILE = Path(__file__).resolve().parent / "holidays.yaml"


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


def load_holidays() -> dict[int, set[date]]:
    with _HOLIDAYS_FILE.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    out: dict[int, set[date]] = {}
    for year, entries in raw.items():
        out[int(year)] = {
            e if isinstance(e, date) else date.fromisoformat(str(e))
            for e in (entries or [])
        }
    return out


def is_trading_day(day: date, holidays: dict[int, set[date]] | None = None) -> bool:
    if day.weekday() >= 5:
        return False
    holidays = load_holidays() if holidays is None else holidays
    return day not in holidays.get(day.year, set())


def resolve_prompt(edition: str, day: date) -> str:
    """Map an edition + date to the prompt template to use.

    Both editions run every day; weekends and NSE holidays switch to the weekend
    templates.
    """
    if edition not in EDITIONS:
        raise ValueError(f"unknown edition: {edition!r} (expected one of {EDITIONS})")

    return edition if is_trading_day(day) else f"weekend_{edition}"

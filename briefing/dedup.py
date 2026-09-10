"""Same-day de-duplication between the morning and evening editions.

Google News is asked for a rolling 24-hour window, not "since the last edition ran",
and NSE announcements / PIB releases simply return whatever is currently listed. Two
editions run hours apart on the same day therefore see largely the same underlying
headlines. This remembers which stories an earlier edition of TODAY already used, so a
later edition of the same day scores only what is actually new.

The state lives on disk as one small JSON file per day (a list of headline keys, not
full stories) and is meant to be committed back to the repo by the CI workflow after
each run, the same way the holiday calendar is — a GitHub Actions runner is thrown away
after every job, so without persisting this somewhere durable, the evening run could
never see what the morning run picked.

Scoped to the same calendar day only: a story that ran yesterday evening is fair game
again this morning. This only stops an edition from repeating what a run *earlier today*
already covered.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

_NORMALISE = re.compile(r"\W+")


def headline_key(item: dict[str, Any]) -> str | None:
    """A stable fingerprint for one story, or None if it has no headline-like text.

    Matches the normalisation the Google News fetcher already uses for its own
    within-fetch dedup, so the same story produces the same key everywhere.
    """
    text = (item.get("headline") or item.get("subject") or "").strip()
    if not text:
        return None
    return _NORMALISE.sub("", text.lower())[:80]


def _state_path(state_dir: Path, day: date) -> Path:
    return state_dir / f"{day.isoformat()}.json"


def load_seen(state_dir: Path, day: date) -> set[str]:
    """Headline keys already used by an earlier edition today. Missing file = none yet."""
    path = _state_path(state_dir, day)
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def record_seen(state_dir: Path, day: date, items: Iterable[dict[str, Any]]) -> None:
    """Add these items' headline keys to today's record. A no-op if there is nothing new."""
    keys = {key for key in (headline_key(item) for item in items) if key}
    if not keys:
        return
    merged = load_seen(state_dir, day) | keys
    state_dir.mkdir(parents=True, exist_ok=True)
    _state_path(state_dir, day).write_text(
        json.dumps(sorted(merged), ensure_ascii=False), encoding="utf-8"
    )

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 25


@dataclass
class FetchResult:
    """Outcome of one source fetch. A failure is data, not an exception:
    the pipeline degrades by omitting sections rather than aborting the run."""

    name: str
    ok: bool
    data: Any = None
    error: str | None = None
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def success(cls, name: str, data: Any) -> "FetchResult":
        return cls(name=name, ok=True, data=data)

    @classmethod
    def failure(cls, name: str, error: str) -> "FetchResult":
        return cls(name=name, ok=False, error=error)

    def __bool__(self) -> bool:
        return self.ok


def with_retries(
    name: str,
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 1.5,
) -> FetchResult:
    last_error = ""
    for attempt in range(attempts):
        try:
            return FetchResult.success(name, fn())
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts - 1:
                time.sleep(base_delay * (2**attempt) + random.uniform(0, 0.75))
    return FetchResult.failure(name, last_error)


def save_raw(results: list[FetchResult], raw_dir: Path, run_id: str) -> Path:
    """Snapshot every source response so a briefing can be audited after the fact."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{run_id}.json"
    payload = {
        r.name: {"ok": r.ok, "error": r.error, "fetched_at": r.fetched_at, "data": r.data}
        for r in results
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path

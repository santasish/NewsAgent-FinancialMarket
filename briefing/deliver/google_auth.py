"""Service-account credentials for the Sheets archive and the Calendar event.

A service account suits these two jobs exactly: it runs headless with no browser consent,
and both targets are files you already own and have shared with it.

It deliberately does NOT cover Google Docs. A service account has no Drive storage quota
on a personal Google account, so `files.create` always fails with `storageQuotaExceeded` —
it can edit your files but never create one. Briefings are delivered by email instead
(see briefing/deliver/mail.py); the reasoning is recorded in SPEC.md.

Scopes are kept to the minimum the two jobs need. No Drive scope is requested.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.events",
]


def _service_account_info() -> dict[str, Any]:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        # Accept raw JSON or base64, since .env files dislike embedded newlines.
        if raw.startswith("{"):
            return json.loads(raw)
        try:
            return json.loads(base64.b64decode(raw))
        except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is neither valid JSON nor valid base64"
            ) from exc

    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    raise RuntimeError(
        "No Google credentials. Set GOOGLE_SERVICE_ACCOUNT_FILE (or "
        "GOOGLE_SERVICE_ACCOUNT_JSON) in .env"
    )


@lru_cache(maxsize=1)
def credentials():
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_info(
        _service_account_info(), scopes=SCOPES
    )


def service_account_email() -> str:
    return _service_account_info().get("client_email", "unknown")


@lru_cache(maxsize=4)
def service(api: str, version: str):
    from googleapiclient.discovery import build

    return build(api, version, credentials=credentials(), cache_discovery=False)

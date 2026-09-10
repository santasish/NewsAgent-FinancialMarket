"""BSE corporate announcements — catches micro-cap order wins and filings NSE misses.

Note: api.bseindia.com redirects to error_Bse.html for requests from some networks
(observed from a non-Indian IP). The fetcher reports the failure and the pipeline omits
the affected items; NSE announcements and the news feed cover much of the same ground.
Expected to work from the Mumbai-region host.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import requests

from briefing.fetch.base import DEFAULT_TIMEOUT, USER_AGENT, FetchResult, with_retries

API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryData/w"
ATTACHMENT_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/corporates/ann.html",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


def fetch_announcements(days_back: int = 1, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    def run() -> list[dict[str, Any]]:
        today = date.today()
        params = {
            "pageno": 1,
            "strCat": -1,
            "strPrevDate": (today - timedelta(days=days_back)).strftime("%Y%m%d"),
            "strScrip": "",
            "strSearch": "P",
            "strToDate": today.strftime("%Y%m%d"),
            "strType": "C",
            "subcategory": -1,
        }
        response = requests.get(API, params=params, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("Table") or []
        out = []
        for row in rows:
            attachment = (row.get("ATTACHMENTNAME") or "").strip()
            out.append(
                {
                    "symbol": row.get("SCRIP_CD"),
                    "company": (row.get("SLONGNAME") or "").strip(),
                    "subject": (row.get("NEWSSUB") or "").strip(),
                    "detail": (row.get("HEADLINE") or "").strip()[:600],
                    "category": (row.get("CATEGORYNAME") or "").strip(),
                    "time": row.get("DT_TM"),
                    "url": ATTACHMENT_BASE + attachment if attachment else None,
                    "source": "BSE",
                }
            )
        if not out:
            raise ValueError("no announcements returned")
        return out

    return with_retries("bse.announcements", run)

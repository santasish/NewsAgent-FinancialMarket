"""Append a run to the Google Sheets archive log.

The archive row itself only has room for a status and a one-line note. The full text of
each issue goes on a second tab, "Issues", in the same spreadsheet — the archive row's
Notes column then carries a link that jumps straight to that row.

This exists in place of a Google Doc: a service account has no Drive storage quota on a
personal Google account, so it can never create a new file, only edit ones you already
own and shared with it. The Spreadsheet is one such file, so a second tab inside it needs
no new permissions and no OAuth — see SPEC.md for the fuller history.
"""

from __future__ import annotations

from functools import lru_cache

from briefing.deliver.google_auth import service

HEADER = ["Date", "Time (IST)", "Edition", "Delivery", "Status", "Notes"]
RANGE = "A:F"

ISSUES_TAB = "Issues"
ISSUES_HEADER = ["Date", "Edition", "Text"]
ISSUES_RANGE = f"{ISSUES_TAB}!A:C"

# A cell tops out at 50,000 characters; a real issue runs a few thousand. This is a
# guard against something going very wrong upstream, not a limit expected in practice.
MAX_CELL_CHARS = 49_000


def ensure_header(sheet_id: str) -> None:
    sheets = service("sheets", "v4")
    existing = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="A1:F1")
        .execute()
        .get("values", [])
    )
    if existing and existing[0]:
        return
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="A1:F1",
        valueInputOption="RAW",
        body={"values": [HEADER]},
    ).execute()


def append_row(
    sheet_id: str,
    *,
    date: str,
    time_ist: str,
    edition: str,
    delivery: str,
    status: str,
    notes: str = "",
) -> None:
    ensure_header(sheet_id)
    service("sheets", "v4").spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=RANGE,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [[date, time_ist, edition, delivery, status, notes]]},
    ).execute()


@lru_cache(maxsize=8)
def _issues_tab_id(sheet_id: str) -> int:
    """The Issues tab's sheetId (gid), creating the tab first if it doesn't exist yet.

    Cached per spreadsheet for the life of the process — a run only ever needs this
    once, and it saves a round trip on every subsequent lookup within the same run.
    """
    sheets = service("sheets", "v4")
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties").execute()
    for sheet in meta.get("sheets", []):
        props = sheet["properties"]
        if props["title"] == ISSUES_TAB:
            return props["sheetId"]

    response = sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": ISSUES_TAB}}}]},
    ).execute()
    tab_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{ISSUES_TAB}!A1:C1",
        valueInputOption="RAW",
        body={"values": [ISSUES_HEADER]},
    ).execute()
    return tab_id


def append_issue(sheet_id: str, *, date: str, edition: str, text: str) -> str:
    """Write the full issue to the Issues tab; return a link straight to that row."""
    tab_id = _issues_tab_id(sheet_id)
    trimmed = text if len(text) <= MAX_CELL_CHARS else text[:MAX_CELL_CHARS] + "\n[truncated]"

    response = (
        service("sheets", "v4")
        .spreadsheets()
        .values()
        .append(
            spreadsheetId=sheet_id,
            range=ISSUES_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[date, edition, trimmed]]},
        )
        .execute()
    )
    # updatedRange looks like "Issues!A5:C5" — the row number is what the link needs.
    updated_range = response["updates"]["updatedRange"]
    cell_ref = updated_range.split("!", 1)[1].split(":", 1)[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={tab_id}&range={cell_ref}"

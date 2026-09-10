"""Append a run to the Google Sheets archive log."""

from __future__ import annotations

from briefing.deliver.google_auth import service

HEADER = ["Date", "Time (IST)", "Edition", "Delivery", "Status", "Notes"]
RANGE = "A:F"


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

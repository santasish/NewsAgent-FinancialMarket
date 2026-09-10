"""Create the calendar event that carries the briefing link."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from briefing.deliver.google_auth import service
from briefing.schedule import IST

DURATION_MINUTES = 15

TITLES = {
    "morning": "📊 Morning Briefing & Trade Game Plan",
    "evening": "📊 Evening Recap & Overnight Setup",
    "weekend_morning": "📊 Weekend Briefing",
    "weekend_evening": "📊 Week-Ahead & Global Wrap",
}


def create_event(
    calendar_id: str,
    *,
    prompt_name: str,
    day: date,
    at: time,
    note: str,
    degraded: bool = False,
) -> dict[str, str]:
    start = datetime.combine(day, at).replace(tzinfo=IST)
    end = start + timedelta(minutes=DURATION_MINUTES)

    summary = TITLES.get(prompt_name, "Market Briefing")
    if degraded:
        summary = f"{summary} (degraded)"

    event = (
        service("calendar", "v3")
        .events()
        .insert(
            calendarId=calendar_id,
            body={
                "summary": summary,
                "description": f"{note}\n\nGenerated automatically by the briefing agent.",
                "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
                "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"},
                "reminders": {"useDefault": False},
            },
        )
        .execute()
    )
    return {"event_id": event["id"], "url": event.get("htmlLink", "")}

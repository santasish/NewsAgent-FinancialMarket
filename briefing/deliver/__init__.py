"""Delivery orchestration: email the briefing, log it, put it on the calendar.

Email is the delivery channel; the archive row and calendar event are bookkeeping around
it. Each is independent and failures are collected rather than raised — a briefing that
reached your inbox but missed the calendar is still delivered, and the run should say so
instead of dying halfway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from briefing.alerts import failure_report, send_alert
from briefing.config import Config
from briefing.deliver.gcal import TITLES, create_event
from briefing.deliver import telegram
from briefing.deliver.gsheets import append_row
from briefing.deliver.mail import send_briefing
from briefing.schedule import IST

EDITION_OF_PROMPT = {
    "morning": "morning",
    "weekend_morning": "morning",
    "evening": "evening",
    "weekend_evening": "evening",
}


@dataclass
class DeliveryResult:
    emailed: bool = False
    telegrammed: bool = False
    event_url: str | None = None
    archived: bool = False
    alert_sent: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def delivered(self) -> bool:
        """Reached you by at least one route."""
        return self.emailed or self.telegrammed

    @property
    def ok(self) -> bool:
        return self.delivered and not self.errors


def edition_time(config: Config, prompt_name: str) -> time:
    edition = EDITION_OF_PROMPT.get(prompt_name, "morning")
    raw = config.get(f"editions.{edition}.time", "08:00")
    hour, _, minute = raw.partition(":")
    return time(int(hour), int(minute or 0))


def deliver(
    config: Config,
    *,
    prompt_name: str,
    day: date,
    body: str,
    degraded: bool,
    verification_ok: bool,
    verification_summary: str,
    failed_sources: list[str],
) -> DeliveryResult:
    result = DeliveryResult()

    # Channels are independent: a briefing that reaches Telegram is delivered even if
    # SMTP is unconfigured, and vice versa. Only a total miss is a failure.
    if telegram.is_configured():
        sent, error = telegram.send_briefing(prompt_name, day, body)
        result.telegrammed = sent
        if not sent and error:
            result.errors.append(f"Telegram: {error}")

    from briefing.alerts import is_configured as email_configured

    if email_configured():
        sent, mail_error = send_briefing(prompt_name, day, body)
        result.emailed = sent
        if not sent and mail_error:
            result.errors.append(f"Email: {mail_error}")

    if not result.delivered and not result.errors:
        result.errors.append("No delivery channel configured (Telegram or email)")

    at = edition_time(config, prompt_name)
    status = "OK" if verification_ok and not degraded else ("DEGRADED" if verification_ok else "VERIFY FAILED")
    notes = "; ".join(failed_sources) if failed_sources else ""
    channels = [c for c, on in (("telegram", result.telegrammed), ("email", result.emailed)) if on]
    link = ", ".join(channels) if channels else "not delivered"

    sheet_id = config.get("google.sheet_id", "")
    if sheet_id:
        try:
            append_row(
                sheet_id,
                date=day.strftime("%d/%m/%Y"),
                time_ist=at.strftime("%I:%M:%S %p"),
                edition=TITLES.get(prompt_name, prompt_name),
                delivery=link,
                status=status,
                notes=notes,
            )
            result.archived = True
        except Exception as exc:
            result.errors.append(f"Sheets archive: {type(exc).__name__}: {exc}")

    calendar_id = config.get("google.calendar_id", "")
    if calendar_id:
        try:
            event = create_event(
                calendar_id,
                prompt_name=prompt_name,
                day=day,
                at=at,
                note=f"Delivered via {link}." if result.delivered else "Delivery FAILED.",
                degraded=degraded,
            )
            result.event_url = event["url"]
        except Exception as exc:
            result.errors.append(f"Calendar: {type(exc).__name__}: {exc}")

    if failed_sources or not verification_ok or result.errors:
        result.alert_sent = send_alert(
            subject=f"[Briefing] {prompt_name} {day.isoformat()} — {status}",
            body=failure_report(
                prompt_name=prompt_name,
                day=day.isoformat(),
                failed_sources=failed_sources,
                verification_ok=verification_ok,
                verification_summary=verification_summary,
                emailed=result.delivered,
                delivery_errors=result.errors,
            ),
        )

    return result


__all__ = ["DeliveryResult", "deliver", "edition_time"]

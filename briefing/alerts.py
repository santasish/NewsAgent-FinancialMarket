"""Outbound email over Gmail SMTP — used for both briefings and failure alerts.

Sending must never take a run down with it: the briefing is already on disk by the time
anything here is called. Every failure is reported and swallowed.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def is_configured() -> bool:
    return all(
        os.environ.get(name, "").strip()
        for name in ("ALERT_EMAIL_FROM", "ALERT_EMAIL_TO", "GMAIL_APP_PASSWORD")
    )


def send_email(
    subject: str,
    text: str,
    html: str | None = None,
    to: str | None = None,
) -> tuple[bool, str | None]:
    """Returns (sent, error). Never raises."""
    sender = os.environ.get("ALERT_EMAIL_FROM", "").strip()
    recipient = (to or os.environ.get("ALERT_EMAIL_TO", "")).strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if not (sender and recipient and password):
        return False, "email not configured (ALERT_EMAIL_FROM/TO, GMAIL_APP_PASSWORD)"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as smtp:
            smtp.login(sender, password)
            smtp.send_message(message)
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP auth rejected — use a Gmail App Password, not the account password"
    except (smtplib.SMTPException, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def send_alert(subject: str, body: str) -> bool:
    """Alert over every configured channel. True if at least one got through."""
    from briefing.deliver import telegram

    delivered = False
    if telegram.is_configured():
        sent, _ = telegram.send_message(f"⚠️ {subject}\n\n{body}"[:4000], html_mode=False)
        delivered = delivered or sent
    if is_configured():
        sent, _ = send_email(subject, body)
        delivered = delivered or sent
    return delivered


def failure_report(
    *,
    prompt_name: str,
    day: str,
    failed_sources: list[str],
    verification_ok: bool,
    verification_summary: str,
    emailed: bool,
    delivery_errors: list[str],
) -> str:
    lines = [f"Briefing run: {prompt_name} for {day}", ""]

    if failed_sources:
        lines += ["Data sources unavailable:", *(f"  - {s}" for s in failed_sources), ""]
    if not verification_ok:
        lines += ["Zero-fabrication check FAILED:", f"  {verification_summary}", ""]
    if delivery_errors:
        lines += ["Delivery problems:", *(f"  - {e}" for e in delivery_errors), ""]

    lines.append("The briefing itself was emailed." if emailed else "The briefing was NOT delivered.")
    return "\n".join(lines)

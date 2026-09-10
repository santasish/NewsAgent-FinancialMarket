"""Deliver the briefing itself as an email.

The issue is plain prose with capital-letter headings, so the HTML part sets it in a
readable proportional face, bolds the headings and keeps the line breaks. Mail clients
that prefer plain text still get the original, unchanged.
"""

from __future__ import annotations

import html as html_escape
from datetime import date

from briefing.alerts import send_email
from briefing.layout import is_heading

SUBJECTS = {
    "morning": "📊 Morning Briefing & Trade Game Plan",
    "evening": "📊 Evening Recap & Overnight Setup",
    "weekend_morning": "📊 Weekend Briefing",
    "weekend_evening": "📊 Week-Ahead & Global Wrap",
}


def _html(body: str) -> str:
    lines = []
    for line in body.splitlines():
        escaped = html_escape.escape(line)
        if is_heading(line):
            lines.append(f'<div style="font-weight:700;margin-top:18px">{escaped}</div>')
        else:
            lines.append(escaped)
    text = "\n".join(lines)
    return f"""<html><body style="margin:0;padding:16px;background:#ffffff">
<div style="font-family:Georgia,'Times New Roman',serif;font-size:15px;line-height:1.55;
white-space:pre-wrap;word-wrap:break-word;color:#111111;max-width:680px">{text}</div>
</body></html>"""


def send_briefing(
    prompt_name: str,
    day: date,
    body: str,
    to: str | None = None,
) -> tuple[bool, str | None]:
    subject = f"{SUBJECTS.get(prompt_name, 'Market Briefing')} — {day.strftime('%d %b %Y')}"
    return send_email(subject, body, html=_html(body), to=to)

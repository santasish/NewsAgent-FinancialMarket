"""Deliver the briefing over the Telegram Bot API.

Telegram caps a message at 4096 characters and an issue runs well past that, so it is
split at its own section headings rather than mid-sentence. Headings go out in bold and
the body as ordinary text, which reads like a newsletter on a phone.

Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Get the token from @BotFather; get the
chat id by messaging the bot once and reading
https://api.telegram.org/bot<TOKEN>/getUpdates
"""

from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request
from datetime import date

from briefing.layout import is_heading, split_sections

API = "https://api.telegram.org/bot{token}/sendMessage"
LIMIT = 3800  # 4096 minus room for the bold tags and a part marker

SUBJECTS = {
    "morning": "📊 Morning Briefing & Trade Game Plan",
    "evening": "📊 Evening Recap & Overnight Setup",
    "weekend_morning": "📊 Weekend Briefing",
    "weekend_evening": "📊 Week-Ahead & Global Wrap",
}


def is_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def split_on_sections(body: str, limit: int = LIMIT) -> list[str]:
    """Pack the issue into message-sized parts, breaking only at section headings."""
    parts: list[str] = []
    current = ""

    for section in split_sections(body):
        piece = section if not current else "\n\n" + section
        if len(current) + len(piece) <= limit:
            current += piece
            continue
        if current:
            parts.append(current)
        piece = section
        # A single section longer than the limit still has to be cut somewhere.
        while len(piece) > limit:
            cut = piece.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            parts.append(piece[:cut])
            piece = piece[cut:].lstrip("\n")
        current = piece

    if current.strip():
        parts.append(current)
    return parts


def render_html(part: str) -> str:
    """Escape the text and bold the heading lines."""
    lines = []
    for line in part.splitlines():
        escaped = html.escape(line)
        lines.append(f"<b>{escaped}</b>" if is_heading(line) else escaped)
    return "\n".join(lines)


def send_message(text: str, *, html_mode: bool = True) -> tuple[bool, str | None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        return False, "telegram not configured (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)"

    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if html_mode:
        payload["parse_mode"] = "HTML"

    request = urllib.request.Request(
        API.format(token=token),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200, None
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read()[:200].decode('utf-8', 'replace')}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def send_briefing(prompt_name: str, day: date, body: str) -> tuple[bool, str | None]:
    title = f"{SUBJECTS.get(prompt_name, 'Market Briefing')} — {day.strftime('%d %b %Y')}"
    parts = split_on_sections(body)

    for index, part in enumerate(parts, start=1):
        header = f"<b>{html.escape(title)}</b>" if index == 1 else ""
        marker = f" <i>({index}/{len(parts)})</i>" if len(parts) > 1 else ""
        lead = f"{header}{marker}\n\n" if header or marker else ""
        text = f"{lead}{render_html(part.strip())}"
        sent, error = send_message(text)
        if not sent:
            return False, f"part {index}/{len(parts)}: {error}"
    return True, None

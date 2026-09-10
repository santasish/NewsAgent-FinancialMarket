"""The shape of a finished issue, shared by every delivery channel.

An issue is plain text. Its first line is the title, every section starts with a heading
written entirely in capital letters on its own line, and nothing else in the text is in
capitals. That one convention is what lets Telegram split a long issue at section
boundaries and lets the email render headings in bold without any markup in the text.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^[A-Z][A-Z0-9 ,:'&()/-]{2,80}$")


def is_heading(line: str) -> bool:
    """A short line of capitals with at least two words, e.g. 'HOW THE DAY WENT'."""
    text = line.strip()
    if not _HEADING.match(text):
        return False
    words = [w for w in re.split(r"\s+", text) if any(c.isalpha() for c in w)]
    return len(words) >= 2


def split_sections(body: str) -> list[str]:
    """Break an issue into its title block followed by one chunk per section.

    Each chunk after the first begins with its heading line. Blank lines around the
    boundary are trimmed so the pieces re-join cleanly.
    """
    sections: list[str] = []
    current: list[str] = []
    for line in body.splitlines():
        if is_heading(line) and any(l.strip() for l in current):
            sections.append("\n".join(current).strip("\n"))
            current = []
        current.append(line)
    if any(l.strip() for l in current):
        sections.append("\n".join(current).strip("\n"))
    return sections

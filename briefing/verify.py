"""Zero-fabrication check: every material number in the briefing must trace to the payload.

Design rule this depends on: the payload builder pre-computes every derived value
(point changes, basis-point moves, percentages, ratios). The model formats numbers,
it never does arithmetic. That keeps this check strict without false positives.

Entity (company / ticker) verification lands in Phase 4.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

# 1,234.56 | 1234.56 | 24,015 | 4.80
_NUMBER = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_URL = re.compile(r"https?://\S+")
# "Nikkei 225", "S&P 500", "FTSE 100": the number is part of the index's name, not a
# figure, and the payload only carries the symbol key (nikkei, sp500).
_NAMED_INDEX = re.compile(
    r"\b(?:nikkei|s&p|ftse|dax|cac|asx|nifty|bse|russell|nasdaq|dow jones|kospi|topix)"
    r"[ -]?\d{2,4}\b",
    re.I,
)
_LIST_MARKER = re.compile(r"^\s*\d+[.)]\s")
_CURRENCY_BEFORE = ("₹", "$")
_SIGN_BEFORE = ("+", "-")
_UNIT_AFTER = ("%", "bps", "bp", "pts", "point", "crore", "cr", "lakh", "strike", "x")


@dataclass(frozen=True)
class Violation:
    number: str
    line_no: int
    line: str


@dataclass
class VerifyResult:
    ok: bool
    violations: list[Violation]
    checked: int

    def summary(self) -> str:
        if self.ok:
            return f"verified {self.checked} numbers against payload: all traceable"
        lines = [f"{len(self.violations)} of {self.checked} numbers not found in payload:"]
        for v in self.violations:
            lines.append(f"  line {v.line_no}: {v.number!r} in {v.line.strip()!r}")
        return "\n".join(lines)


def _walk(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _walk(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
    elif node is not None and not isinstance(node, bool):
        yield str(node)


def payload_numbers(payload: dict[str, Any]) -> set[float]:
    values: set[float] = set()
    for text in _walk(payload):
        for token in _NUMBER.findall(text):
            values.add(float(token.replace(",", "")))
    return values


def _is_material(literal: str, line: str, start: int, end: int, min_magnitude: float) -> bool:
    if "," in literal or "." in literal:
        return True
    previous = line[start - 1] if start else ""
    if previous in _CURRENCY_BEFORE:
        return True
    # A leading +/- only marks a signed figure when it is not a hyphen inside a word.
    # Without this, the template's own "Post-3:30 PM" header reads as the datum "3".
    if previous in _SIGN_BEFORE:
        preceding = line[start - 2] if start > 1 else ""
        if not preceding.isalnum():
            return True

    after = line[end : end + 8].lower().lstrip()
    if any(after.startswith(u) for u in _UNIT_AFTER):
        return True
    return float(literal) >= min_magnitude


def _matches(value: float, literal: str, candidates: set[float], tolerance: float) -> bool:
    if value in candidates:
        return True
    decimals = len(literal.partition(".")[2])
    scale = 10**decimals
    for candidate in candidates:
        if abs(candidate - value) <= tolerance * max(1.0, abs(candidate)):
            return True
        # The model may round or truncate a payload value when formatting it.
        if round(candidate, decimals) == value:
            return True
        if int(candidate * scale) / scale == value:
            return True
    return False


def verify(
    output: str,
    payload: dict[str, Any],
    *,
    tolerance: float = 0.001,
    min_magnitude: float = 100.0,
) -> VerifyResult:
    candidates = payload_numbers(payload)
    violations: list[Violation] = []
    checked = 0

    for line_no, raw_line in enumerate(output.splitlines(), start=1):
        line = _NAMED_INDEX.sub(lambda m: re.sub(r"\d", " ", m.group()), _URL.sub("", raw_line))
        body_start = _LIST_MARKER.match(line)
        offset = body_start.end() if body_start else 0
        for match in _NUMBER.finditer(line, offset):
            literal = match.group()
            if not _is_material(literal, line, match.start(), match.end(), min_magnitude):
                continue
            checked += 1
            value = float(literal.replace(",", ""))
            if not _matches(value, literal, candidates, tolerance):
                violations.append(Violation(literal, line_no, raw_line))

    return VerifyResult(ok=not violations, violations=violations, checked=checked)


def violations_feedback(result: VerifyResult) -> str:
    """Correction message fed back to the model on a regeneration attempt."""
    offending = sorted({v.number for v in result.violations})
    return (
        "Your previous output failed the zero-fabrication check. These numbers do not "
        "appear in the input payload: " + ", ".join(offending) + ". "
        "Regenerate the report using only values present in the payload. Do not perform "
        "arithmetic to derive new figures. If a figure is unavailable, omit the line."
    )


def load_payload(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

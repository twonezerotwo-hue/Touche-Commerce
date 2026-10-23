"""Handling of untrusted text on its way to the model.

Free text stored in the database (names, notes, descriptions, supplier messages,
document titles) was written by someone other than the operator. It reaches the model
only through this module:

* control, zero-width and bidirectional-override characters are removed (they hide
  instructions from a human reviewer);
* the length is bounded;
* text that reads like an instruction to an AI is **withheld** and replaced by a
  neutral marker, and the occurrence is recorded as a safety flag on the run.

This is one layer. The controls that actually matter do not depend on the model
behaving: the tool registry only exposes read-only tools, the company is fixed by the
server, every tool re-checks the caller's permission, and the response validator
removes anything not backed by a tool result.
"""

from __future__ import annotations

import re
import unicodedata

WITHHELD = "[content withheld: instruction-like text detected in a stored record]"

_BIDI_AND_INVISIBLE = {
    "​", "‌", "‍", "⁠", "﻿", "­",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩",
}  # fmt: skip

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "INSTRUCTION_OVERRIDE",
        re.compile(
            r"(ignore|disregard|forget|override|bypass)\b.{0,40}\b"
            r"(previous|prior|above|earlier|all|your|system|safety)\b.{0,40}"
            r"\b(instruction|prompt|rule|guideline|polic|restriction|message)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "ROLE_IMPERSONATION",
        re.compile(
            r"(\bsystem\s*(prompt|message|override)\b|\bdeveloper\s+mode\b|\bjailbreak\b|"
            r"\byou\s+are\s+now\b|\bact\s+as\s+(an?\s+)?(admin|root|system|developer)\b|"
            r"<\|?\s*(im_start|im_end|system|assistant)\s*\|?>|\[/?(INST|SYS)\])",
            re.IGNORECASE,
        ),
    ),
    (
        "TOOL_DIRECTIVE",
        re.compile(
            r"(\b(call|invoke|run|execute|use)\b.{0,30}\b(tool|function|command|sql|shell)\b|"
            r"\bcompany[_\s-]?id\s*[:=]|\bswitch\s+(to\s+)?(another\s+)?company\b)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "ACTION_DIRECTIVE",
        re.compile(
            r"\b(approve|authori[sz]e|release|wire|transfer|pay|send|sign|delete|mark)\b"
            r".{0,40}\b(payment|invoice|funds|money|email|contract|order|deal|record|won|"
            r"journal|account)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "SECRET_REQUEST",
        re.compile(
            r"\b(reveal|print|show|leak|exfiltrat\w*|send)\b.{0,40}\b"
            r"(password|api[\s_-]?key|secret|token|credential|system prompt|cookie)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "DATA_EXFILTRATION",
        re.compile(
            r"(https?://\S+\?\S*=|!\[[^\]]*\]\(https?://|\bcurl\b|\bfetch\()", re.IGNORECASE
        ),
    ),
)


# An action word near a business noun ("send the invoice") is ordinary in trade notes,
# so it is recorded as a flag but the text is kept; the model has no tool that could
# act on it anyway. The other patterns have no legitimate place in a stored record.
_ADVISORY_ONLY = frozenset({"ACTION_DIRECTIVE"})


def clean_text(value: str, *, limit: int) -> str:
    """Remove hidden/control characters and bound the length."""
    kept: list[str] = []
    for ch in unicodedata.normalize("NFC", value):
        if ch in _BIDI_AND_INVISIBLE:
            continue
        if ch in "\n\t" or unicodedata.category(ch)[0] != "C":
            kept.append(ch)
    text = "".join(kept).strip()
    return text[:limit]


def injection_flags(value: str) -> list[str]:
    """Names of the instruction-like patterns found in ``value`` (empty when clean)."""
    return [name for name, pattern in _PATTERNS if pattern.search(value)]


def untrusted(value: str | None, *, limit: int = 300) -> tuple[str | None, list[str]]:
    """Make stored free text safe to show the model; returns ``(text, flags)``."""
    if value is None:
        return None, []
    text = clean_text(value, limit=limit)
    flags = injection_flags(text)
    if any(flag not in _ADVISORY_ONLY for flag in flags):
        return WITHHELD, flags
    return text, flags


class Sanitiser:
    """Collects the flags raised while one tool result is being built."""

    def __init__(self) -> None:
        self.flags: list[str] = []

    def text(self, value: str | None, *, limit: int = 300) -> str | None:
        cleaned, flags = untrusted(value, limit=limit)
        for flag in flags:
            if flag not in self.flags:
                self.flags.append(flag)
        return cleaned

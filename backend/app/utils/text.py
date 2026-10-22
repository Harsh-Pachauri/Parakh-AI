"""Utilities for transcript cleanup and privacy redaction."""

from __future__ import annotations

import re

FILLER_WORDS = {"um", "uh", "erm", "er"}


def clean_transcript(text: str) -> str:
    """Strip filler words, normalize whitespace, and tidy punctuation."""
    cleaned = text or ""
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(filler)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = cleaned.strip()
    cleaned = re.sub(
        r"(^|[.!?]\s+)([a-z])",
        lambda match: f"{match.group(1)}{match.group(2).upper()}",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and not cleaned.endswith((".", "!", "?")):
        cleaned += "."
    return cleaned


def anonymise(text: str) -> str:
    """Replace student-identifying details with redaction placeholders."""
    redacted = text or ""
    redacted = re.sub(
        r"\bmy name is\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*",
        "my name is [STUDENT]",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"\b(?:roll|reg(?:istration)?|student id)\s*[:#-]?\s*\d{4}[A-Za-z]{2,4}\d{2,5}\b",
        "roll [REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL]",
        redacted,
    )
    redacted = re.sub(
        r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{3}[-.\s]?){2}\d{4}\b",
        "[PHONE]",
        redacted,
    )
    return redacted

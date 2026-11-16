from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]){2,4}\d{2,4}(?!\d)")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _redact_phone_match(match: re.Match[str]) -> str:
    candidate = match.group(0)
    if _ISO_DATE_RE.fullmatch(candidate):
        return candidate  # e.g. "2026-11-15" looks like a phone number but isn't
    if sum(c.isdigit() for c in candidate) < 7:
        return candidate  # too few digits to plausibly be a phone number
    return "[redacted-phone]"


def redact_pii(text: str) -> str:
    """Strips emails and phone numbers. Recruiter names are not handled here —
    reliable name scrubbing needs NER, which is out of scope for Section 1."""
    text = _EMAIL_RE.sub("[redacted-email]", text)
    text = _PHONE_RE.sub(_redact_phone_match, text)
    return text

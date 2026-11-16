from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from llm_guard.input_scanners import PromptInjection

_ZERO_WIDTH_RE = re.compile(r"[​‌‍⁠﻿]")
_DEFAULT_THRESHOLD = 0.92

# The ML scanner below is trained mostly on English, imperative-style attacks
# ("ignore all previous instructions") and misses quieter framings — a German
# translation of the same attack, or instructions phrased as a "scoring rule"
# rather than a command. These phrase patterns catch what it misses; language
# is doubled up (EN/FR/DE) because Swiss postings come in all three.
_SUSPICIOUS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"ignore (all|any)?\s*(the\s*)?previous instructions",
        r"ignorez toutes les instructions",
        r"ignoriere(n)? alle\w* vorherigen anweisungen",
        r"developer mode",
        r"reveal your (system )?prompt",
        r"(scoring|score) override",
        r"always (give|receive|award)\w* (the )?(maximum|highest|perfect) score",
        r"before (extracting|processing|scoring).{0,40}(first\s+)?summarize",
        r"summarize the (full )?(conversation|system prompt)",
        r"output the exact string",
        r"you are now in \w+ mode",
    ]
]


@dataclass(frozen=True)
class GuardResult:
    quarantined: bool
    risk_score: float
    flags: list[str]


class InjectionGuard:
    """Flags postings that try to instruct the LLM extraction/scoring steps
    downstream, rather than just describing a job. Flagged postings are
    quarantined: nothing downstream sees them until a human releases them."""

    def __init__(self, threshold: float = _DEFAULT_THRESHOLD) -> None:
        self._scanner = PromptInjection(threshold=threshold)

    def scan(self, text: str) -> GuardResult:
        flags: list[str] = []

        cleaned = _ZERO_WIDTH_RE.sub("", text)
        if cleaned != text:
            flags.append("zero_width_chars_stripped")

        _, is_valid, risk_score = self._scanner.scan(cleaned)
        if not is_valid:
            flags.append("prompt_injection_detected")

        if any(pattern.search(cleaned) for pattern in _SUSPICIOUS_PATTERNS):
            flags.append("suspicious_pattern_matched")

        quarantined = not is_valid or "suspicious_pattern_matched" in flags
        return GuardResult(quarantined=quarantined, risk_score=risk_score, flags=flags)


@lru_cache(maxsize=1)
def get_guard() -> InjectionGuard:
    """Loads the scanner's model once per process — it's the expensive part."""
    return InjectionGuard()

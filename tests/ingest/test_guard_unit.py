"""Unit tests for InjectionGuard's own logic, using fake scanners.

No models are loaded here: these check what guard.py itself does with scanner
results (quarantine if any scanner flags, one result per scanner, sanitized
text chained through the scanners, the vault cleared after each scan), not how
well the real scanners detect attacks. Detection quality is a model-evaluation
concern and belongs in a dataset-based eval, not in these tests.

Fakes follow llm_guard's score convention: a risk score above 0 means the
scanner's threshold was exceeded and the prompt is invalid; 0 or below means
it passed.
"""

from __future__ import annotations

import pytest

from jobfit.ingest.guard import InjectionGuard


class _FakeScanner:
    def __init__(self, score: float, rewrite: str | None = None) -> None:
        self.score = score
        self.rewrite = rewrite
        self.received: str | None = None

    def scan(self, prompt: str) -> tuple[str, bool, float]:
        self.received = prompt
        sanitized = prompt if self.rewrite is None else self.rewrite
        return sanitized, self.score <= 0, self.score


def _fake(name: str, score: float, rewrite: str | None = None) -> _FakeScanner:
    # llm_guard's scan_prompt keys results by type(scanner).__name__, so each
    # fake needs its own class name to get its own entry.
    return type(name, (_FakeScanner,), {})(score, rewrite)


def test_positive_score_quarantines():
    result = InjectionGuard([_fake("Attack", score=0.9)]).scan("posting")
    assert result.quarantined


def test_non_positive_score_does_not_quarantine():
    result = InjectionGuard([_fake("Clean", score=-1.0), _fake("Zero", score=0.0)]).scan("posting")
    assert not result.quarantined


@pytest.mark.parametrize("flagged_position", [0, 1, 2])
def test_any_single_flagged_scanner_quarantines(flagged_position: int):
    scores = [-1.0, -1.0, -1.0]
    scores[flagged_position] = 0.8
    scanners = [_fake(f"Scanner{i}", score) for i, score in enumerate(scores)]
    result = InjectionGuard(scanners).scan("posting")
    assert result.quarantined


def test_results_have_one_entry_per_scanner_with_scores_passed_through():
    scanners = [_fake("First", score=-0.5), _fake("Second", score=0.7)]
    result = InjectionGuard(scanners).scan("posting")
    assert [(r.scanner, r.score, r.flagged) for r in result.results] == [
        ("First", -0.5, False),
        ("Second", 0.7, True),
    ]


def test_each_scanner_receives_previous_scanners_sanitized_output():
    first = _fake("Redactor", score=-1.0, rewrite="redacted")
    second = _fake("Stripper", score=-1.0, rewrite="redacted and stripped")
    third = _fake("Detector", score=-1.0)
    result = InjectionGuard([first, second, third]).scan("original")
    assert first.received == "original"
    assert second.received == "redacted"
    assert third.received == "redacted and stripped"
    assert result.sanitized_text == "redacted and stripped"


def test_flagged_scanner_does_not_stop_later_scanners():
    """Every scanner runs even after one flags, so guard_results always has
    the full set of per-scanner scores for the review page."""
    last = _fake("Last", score=-1.0)
    result = InjectionGuard([_fake("Attack", score=0.9), last]).scan("posting")
    assert last.received == "posting"
    assert len(result.results) == 2


def test_vault_is_cleared_after_each_scan():
    """Redaction is one-way: whatever Anonymize stashes in the vault (the
    original PII, recoverable by deanonymizing) must not outlive the scan."""
    guard = InjectionGuard([])

    class Stasher(_FakeScanner):
        def scan(self, prompt: str) -> tuple[str, bool, float]:
            guard._vault.append(("[REDACTED_EMAIL_1]", "someone@example.com"))  # pylint: disable=protected-access
            return super().scan(prompt)

    guard._scanners = [Stasher(score=-1.0)]  # pylint: disable=protected-access
    guard.scan("posting")
    assert guard._vault.get() == []  # pylint: disable=protected-access


def test_blank_posting_is_not_quarantined_and_has_no_results():
    """llm_guard's scan_prompt skips every scanner on blank input, so a blank
    posting gets no per-scanner rows at all, even with a scanner that would
    flag anything."""
    result = InjectionGuard([_fake("Attack", score=0.9)]).scan("   ")
    assert not result.quarantined
    assert result.results == []

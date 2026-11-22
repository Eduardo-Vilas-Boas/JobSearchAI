"""Unit tests for InjectionGuard's own logic, using fake scanners.

No models are loaded here: these check what guard.py itself does with scanner
results (quarantine if any scanner flags, one result per scanner, sanitized
text chained through the scanners), not how
well the real scanners detect attacks. Detection quality is a model-evaluation
concern and belongs in a dataset-based eval, not in these tests.

Fakes (tests/fakes.py) flag the text when their score is above 0.
"""

from __future__ import annotations

import pytest

from jobfit.ingest.guard import InjectionGuard
from tests.fakes import fake_scanner as _fake


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

import pytest

from jobfit.ingest.guard import InjectionGuard
from tests.fixtures.adversarial_postings import ADVERSARIAL_POSTINGS, BENIGN_POSTINGS


@pytest.fixture(scope="module")
def guard() -> InjectionGuard:
    return InjectionGuard()


@pytest.mark.parametrize("posting", ADVERSARIAL_POSTINGS)
def test_guard_quarantines_adversarial_postings(guard: InjectionGuard, posting: str):
    result = guard.scan(posting)
    assert result.quarantined, f"guard missed an injection attempt: {posting[:60]!r}..."


@pytest.mark.parametrize("posting", BENIGN_POSTINGS)
def test_guard_does_not_quarantine_benign_postings(guard: InjectionGuard, posting: str):
    result = guard.scan(posting)
    assert not result.quarantined, f"false positive on a clean posting: {posting[:60]!r}..."


def test_guard_strips_zero_width_characters_before_scoring(guard: InjectionGuard):
    text = "Senior ML Engineer​ - Zurich. A normal, benign posting about ML work."
    result = guard.scan(text)
    assert "zero_width_chars_stripped" in result.flags

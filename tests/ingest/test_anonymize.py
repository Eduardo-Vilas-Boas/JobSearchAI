"""Tests for the PII redaction step (runs before the guard, never quarantines).

Redaction uses Presidio's pattern recognizers for email addresses and phone
numbers only, with no name detection (NER): the PII that matters in a job
posting is a recruiter's contact details, and NER misread place and company
names ("Geneva", "Sonar") as people. These tests check that configuration,
not Presidio's own detection quality, and don't pin the placeholder text.
"""

import pytest

from jobfit.ingest.anonymize import Anonymizer


@pytest.fixture(scope="module")
def anonymizer() -> Anonymizer:
    return Anonymizer()


def test_redacts_email(anonymizer: Anonymizer):
    text = anonymizer.anonymize(
        "Data Scientist - Geneva. Send your CV to hiring.manager@example.com."
    )
    assert "hiring.manager@example.com" not in text
    assert "Send your CV to" in text


def test_redacts_swiss_phone_number(anonymizer: Anonymizer):
    """Postings are mostly Swiss, so Swiss numbers must be recognized."""
    text = anonymizer.anonymize("Questions? Call our recruiting team on +41 44 668 18 00.")
    assert "668 18 00" not in text
    assert "Call our recruiting team on" in text


def test_leaves_names_places_and_companies_alone(anonymizer: Anonymizer):
    """No name detection: only contact details count as PII here."""
    text = "Site Reliability Engineer at Sonar in Geneva. Your manager will be Anna Müller."
    assert anonymizer.anonymize(text) == text


def test_text_without_pii_is_unchanged(anonymizer: Anonymizer):
    text = "Senior ML Engineer - Zurich.\nBuild production ML systems with PyTorch."
    assert anonymizer.anonymize(text) == text

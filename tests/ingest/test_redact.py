from jobfit.ingest.redact import redact_pii


def test_redacts_email():
    text = "Send your CV to hiring.manager@example.com for consideration."
    assert "hiring.manager@example.com" not in redact_pii(text)
    assert "[redacted-email]" in redact_pii(text)


def test_redacts_swiss_phone_number():
    text = "Questions? Call us at +41 44 123 45 67 or 044 123 45 67."
    redacted = redact_pii(text)
    assert "123 45 67" not in redacted
    assert "[redacted-phone]" in redacted


def test_does_not_redact_iso_date():
    text = "Applications open 2026-11-15."
    assert redact_pii(text) == text


def test_does_not_redact_workload_percentage_range():
    text = "This role is 80-100% workload."
    assert redact_pii(text) == text

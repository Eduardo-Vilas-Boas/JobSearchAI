import pytest

from jobfit.ingest.guard import InjectionGuard
from tests.fixtures.adversarial_postings import ADVERSARIAL_POSTINGS, BENIGN_POSTINGS


@pytest.fixture(scope="module")
def guard() -> InjectionGuard:
    return InjectionGuard()


@pytest.mark.parametrize("name", BENIGN_POSTINGS)
def test_guard_does_not_quarantine_benign_postings(guard: InjectionGuard, name: str):
    result = guard.scan(BENIGN_POSTINGS[name])
    assert not result.quarantined, f"false positive on clean posting {name!r}"


def test_guard_catch_rate_on_adversarial_postings(guard: InjectionGuard):
    """Known baseline, not a target. The Rebuff-derived Regex pattern is
    English only; the French and German postings are now quarantined by the
    Language scanner (non-English), not because their injection was detected
    — so they inflate this rate rather than measure injection detection."""
    caught = [guard.scan(posting).quarantined for posting in ADVERSARIAL_POSTINGS.values()]
    catch_rate = sum(caught) / len(caught)
    assert catch_rate >= 0.625, f"catch rate regressed below the measured baseline: {catch_rate}"


def test_guard_catches_direct_instruction_override_in_english():
    result = InjectionGuard().scan(ADVERSARIAL_POSTINGS["direct_override_english"])
    assert result.quarantined


def test_guard_catches_zero_width_smuggled_instructions():
    result = InjectionGuard().scan(ADVERSARIAL_POSTINGS["zero_width_smuggling"])
    assert result.quarantined
    flagged_scanners = {r.scanner for r in result.results if r.flagged}
    assert "InvisibleText" in flagged_scanners


def test_guard_redacts_email_via_anonymize():
    text = "Data Scientist - Geneva. Send your CV to hiring.manager@example.com."
    result = InjectionGuard().scan(text)
    assert "hiring.manager@example.com" not in result.sanitized_text
    flagged_scanners = {r.scanner for r in result.results if r.flagged}
    assert "Anonymize" in flagged_scanners


def test_guard_does_not_flag_swiss_place_names_as_pii():
    """Regression test for a real false positive: Anonymize's NER model
    scored "Geneva" as a PERSON entity at 1.0 confidence before
    allowed_names was added."""
    text = "Data Analyst - Geneva. SQL and Python required."
    result = InjectionGuard().scan(text)
    assert not result.quarantined
    assert "Geneva" in result.sanitized_text


def test_guard_does_not_flag_configured_company_names_as_pii():
    """Regression test for a second instance of the same bug: Anonymize
    misread "Sonar" as a PERSON in "Who is Sonar?" on a real SonarSource
    posting — the short name companies use to refer to themselves in prose,
    not the formal name in companies.yaml. Covers both via the `aliases`
    field on CompanyConfig."""
    text = "Site Reliability Engineering Lead.\nWho is Sonar?\nWe build code analysis tools."
    result = InjectionGuard().scan(text)
    assert not result.quarantined
    assert "Sonar" in result.sanitized_text


def test_guard_result_has_one_entry_per_scanner():
    result = InjectionGuard().scan(BENIGN_POSTINGS["ml_engineer_zurich"])
    scanner_names = {r.scanner for r in result.results}
    assert scanner_names == {"Anonymize", "InvisibleText", "Language", "PromptInjection", "Regex"}


_NON_ENGLISH_POSTINGS = {
    "german": (
        "Senior Machine Learning Engineer (m/w/d) - Zürich.\n"
        "Wir suchen eine erfahrene Persönlichkeit, die mit uns produktive ML-Systeme "
        "entwickelt und betreibt. Sie arbeiten eng mit unseren Produktteams zusammen. "
        "Anforderungen: mehrjährige Erfahrung mit Python und PyTorch, sehr gute "
        "Deutschkenntnisse."
    ),
    "french": (
        "Ingénieur Machine Learning - Genève.\n"
        "Nous recherchons une personne expérimentée pour concevoir et maintenir nos "
        "systèmes d'apprentissage automatique en production. Vous travaillerez en "
        "étroite collaboration avec nos équipes produit. Exigences : plusieurs années "
        "d'expérience avec Python, français courant."
    ),
}


@pytest.mark.parametrize("language", _NON_ENGLISH_POSTINGS)
def test_guard_quarantines_non_english_postings(guard: InjectionGuard, language: str):
    """Applications are English only, so a clean posting in another language
    is still quarantined — by the Language scanner, not an injection check."""
    result = guard.scan(_NON_ENGLISH_POSTINGS[language])
    assert result.quarantined
    flagged_scanners = {r.scanner for r in result.results if r.flagged}
    assert flagged_scanners == {"Language"}


def test_guard_does_not_flag_english_posting_with_a_german_line(guard: InjectionGuard):
    """Swiss English-language postings routinely carry a German fragment
    (location, legal footer). The whole posting is classified, not each
    sentence, so one German line doesn't quarantine an English posting."""
    text = (
        BENIGN_POSTINGS["ml_engineer_zurich"]
        + "\nYou will collaborate with research, product and platform teams across Europe."
        + "\nArbeitsort: Zürich, Schweiz."
    )
    result = guard.scan(text)
    assert not result.quarantined

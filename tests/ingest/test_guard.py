import pytest

from jobfit.ingest.guard import InjectionGuard
from tests.fixtures.adversarial_postings import ADVERSARIAL_POSTINGS, BENIGN_POSTINGS


@pytest.fixture(scope="module")
def guard() -> InjectionGuard:
    return InjectionGuard()


def test_default_guard_runs_the_hidden_text_check_and_one_injection_classifier(
    guard: InjectionGuard,
):
    """One injection classifier at its default threshold, plus the hidden
    character check. The classifier's name stays "PromptInjection" whichever
    model backs it, so guard_results stays comparable across a model swap."""
    result = guard.scan(BENIGN_POSTINGS["ml_engineer_zurich"])
    assert [r.scanner for r in result.results] == ["InvisibleText", "PromptInjection"]


@pytest.mark.parametrize("name", BENIGN_POSTINGS)
def test_guard_does_not_quarantine_benign_postings(guard: InjectionGuard, name: str):
    result = guard.scan(BENIGN_POSTINGS[name])
    assert not result.quarantined, f"false positive on clean posting {name!r}"


def test_guard_quarantines_a_plain_instruction_override(guard: InjectionGuard):
    """Checks the wiring, not how good the model is: the right model loads,
    its attack class is read as the attack class (a wrong index would flip
    every verdict), and a flag quarantines the posting. How many of the
    adversarial fixtures the model catches is a measurement of the model,
    recorded in docs/ (0006), not a test: nothing in this code could fix it."""
    result = guard.scan(ADVERSARIAL_POSTINGS["direct_override_english"])
    assert result.quarantined


def test_guard_quarantines_zero_width_smuggled_instructions(guard: InjectionGuard):
    result = guard.scan(ADVERSARIAL_POSTINGS["zero_width_smuggling"])
    assert result.quarantined


# Real postings often run past the classifier's 512-token window; the fixtures
# above are all under 50 words. Repeating the benign postings gives a clean
# posting of about 750 words.
_LONG_BENIGN_POSTING = "\n\n".join(list(BENIGN_POSTINGS.values()) * 8)


def test_guard_does_not_quarantine_a_long_clean_posting(guard: InjectionGuard):
    assert not guard.scan(_LONG_BENIGN_POSTING).quarantined


def test_guard_catches_an_attack_past_the_first_512_tokens(guard: InjectionGuard):
    """Text past the window must still be scanned, not cut off."""
    attack = ADVERSARIAL_POSTINGS["direct_override_english"].split("\n", 1)[1]
    result = guard.scan(f"{_LONG_BENIGN_POSTING}\n\n{attack}")
    assert result.quarantined


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
def test_guard_does_not_quarantine_non_english_postings(guard: InjectionGuard, language: str):
    """Applications go to jobs across Europe, so a clean posting in another
    language is a normal posting, not a reason to quarantine."""
    result = guard.scan(_NON_ENGLISH_POSTINGS[language])
    assert not result.quarantined, f"false positive on clean {language} posting"

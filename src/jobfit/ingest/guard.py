from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from llm_guard import scan_prompt
from llm_guard.input_scanners import Anonymize, InvisibleText, PromptInjection, Regex
from llm_guard.vault import Vault

from jobfit.config import load_companies

# Phrase structure adapted from Rebuff's generateInjectionKeywords()
# (https://github.com/protectai/rebuff, MIT License, ProtectAI): verb +
# optional "prior/previous/..." qualifier + object noun, e.g. "ignore
# previous instructions", "disregard prior context". A credited public
# pattern, not one written for this project — English only, so it does not
# cover the French/German phrasings the PromptInjection model was found to
# miss earlier; that gap should be re-measured against the adversarial set,
# not assumed fixed.
_REBUFF_OVERRIDE_PATTERN = (
    r"\b(?:ignore|disregard|skip|forget|neglect|overlook|omit|bypass"
    r"|pay no attention to|do not follow|do not obey)\b"
    r"(?:\s+\w+){0,2}?\s*"
    r"\b(?:prior|previous|preceding|above|foregoing|earlier|initial)?\b\s*"
    r"\b(?:content|text|instructions?|directives?|commands?|context"
    r"|conversation|inputs?|data|messages?|communication|responses?|requests?)\b"
)

# Measured, not guessed: Anonymize's NER model misreads Swiss place names as
# PERSON entities (e.g. "Geneva" in "Data Analyst - Geneva." scored 1.0
# confidence) — a real false positive found while testing against this
# project's own postings, not a hypothetical. `allowed_names` maps straight
# to Presidio's `allow_list`, an exemption the scanner itself exposes, so
# this is config, not a custom recognizer. Extend as new cities show up in
# `config/companies.yaml`.
_SWISS_PLACE_NAMES = [
    "Zurich",
    "Zürich",
    "Geneva",
    "Genève",
    "Basel",
    "Bern",
    "Berne",
    "Lausanne",
    "Lucerne",
    "Luzern",
    "Lugano",
    "Zug",
    "St. Gallen",
    "Winterthur",
    "Fribourg",
    "Freiburg",
    "Neuchâtel",
    "Biel",
    "Bienne",
    "Thun",
    "Baden",
    "Schaffhausen",
    "Chur",
    "Sion",
    "Davos",
    "Montreux",
    "Nyon",
    "Rapperswil",
    "Vaud",
    "Ticino",
    "Valais",
    "Aargau",
]


def _allowed_names() -> list[str]:
    """Same bug, same fix, a second time: Anonymize also misread the company
    names themselves as PERSON entities ("Who is Sonar?" -> "Who is
    [REDACTED_PERSON_1]?", found on real live postings). Company names come
    from config/companies.yaml so this stays correct as that list grows,
    instead of being a second hardcoded list to maintain by hand."""
    names = list(_SWISS_PLACE_NAMES)
    for company in load_companies():
        names.append(company.name)
        names.extend(company.aliases)
    return names


@dataclass(frozen=True)
class ScannerResult:
    scanner: str
    score: float
    flagged: bool


@dataclass(frozen=True)
class GuardScanResult:
    quarantined: bool
    sanitized_text: str
    results: list[ScannerResult]


class InjectionGuard:
    """Runs postings through LLM Guard's off-the-shelf input scanners.

    No custom detection logic: PromptInjection and InvisibleText run with
    their library defaults, Anonymize's PII detection is its own default NER
    model, and Regex is seeded with a credited public pattern rather than one
    written for this project. A posting is quarantined if any scanner flags
    it — stored, not discarded, so a human can review and release it.

    Scanners run in sequence and each one's sanitized output feeds the next
    (Anonymize's PII redaction happens before InvisibleText's character
    stripping, before the injection checks), so `sanitized_text` is the
    fully-cleaned result of the whole chain, not just the last scanner.
    """

    def __init__(self) -> None:
        self._vault = Vault()
        self._scanners = [
            Anonymize(self._vault, allowed_names=_allowed_names()),
            InvisibleText(),
            PromptInjection(),
            Regex(patterns=[_REBUFF_OVERRIDE_PATTERN]),
        ]

    def scan(self, text: str) -> GuardScanResult:
        sanitized, results_valid, results_score = scan_prompt(self._scanners, text)
        results = [
            ScannerResult(scanner=name, score=results_score[name], flagged=not is_valid)
            for name, is_valid in results_valid.items()
        ]
        # Vault has no reset method; get() returns the live list, so clearing
        # it in place discards whatever Anonymize just stashed. We want
        # one-way redaction, not a way to recover the PII we stripped.
        self._vault.get().clear()
        return GuardScanResult(
            quarantined=any(r.flagged for r in results),
            sanitized_text=sanitized,
            results=results,
        )


@lru_cache(maxsize=1)
def get_guard() -> InjectionGuard:
    """Loads the scanners' models once per process — that's the expensive part."""
    return InjectionGuard()

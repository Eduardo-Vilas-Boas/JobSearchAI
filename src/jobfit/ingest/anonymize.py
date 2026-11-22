"""PII redaction: the pipeline step between normalization and the guard.

Uses Microsoft Presidio's off-the-shelf pattern recognizers for email
addresses and phone numbers, and nothing else: the PII that matters in a job
posting is a recruiter's contact details. There's no name detection (NER):
llm-guard's NER-based Anonymize, used before, misread place and company names
("Geneva", "Sonar") as people.

It only redacts and never flags or quarantines a posting: a PII hit isn't an
attack, and once redacted it's no longer a risk. Runs before the guard, so
neither the guard nor any later LLM step ever sees the original PII, and
stored text is redacted.

The recognizers are called directly rather than through Presidio's
AnalyzerEngine, because the engine always loads a spaCy model, which pattern
recognizers don't need.
"""

from __future__ import annotations

from functools import lru_cache

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer
from presidio_anonymizer import AnonymizerEngine

# Presidio's default phone regions are mostly outside Europe and don't include
# Switzerland. These are the countries applications go to; numbers written in
# international form (+41 ...) are matched whatever the region list.
PHONE_REGIONS = ("CH", "DE", "FR", "IT", "AT", "GB", "NL", "BE", "ES", "IE")


class Anonymizer:
    def __init__(self) -> None:
        self._recognizers: list[EntityRecognizer] = [
            EmailRecognizer(),
            PhoneRecognizer(supported_regions=PHONE_REGIONS),
        ]
        self._anonymizer = AnonymizerEngine()

    def anonymize(self, text: str) -> str:
        results: list[RecognizerResult] = []
        for recognizer in self._recognizers:
            results += recognizer.analyze(text, recognizer.supported_entities)
        return self._anonymizer.anonymize(text=text, analyzer_results=results).text


@lru_cache(maxsize=1)
def get_anonymizer() -> Anonymizer:
    """One instance per process."""
    return Anonymizer()

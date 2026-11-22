"""Prompt-injection guard: the pipeline step between PII redaction and storage.

Two checks, each with its default decision rule and no tuning:
- InvisibleText: strips hidden Unicode characters (zero-width spaces, tag
  characters, private-use characters) and flags the posting if it found any.
  Ported from LLM Guard's scanner of the same name (MIT), which is no longer
  maintained.
- PromptInjection: one Hugging Face classifier, run directly with
  transformers. For now protectai/deberta-v3-base-prompt-injection-v2
  (Apache 2.0, mainly English); planned: Meta's Llama Prompt Guard 2 86M,
  trained on several languages, once access to that gated model is approved.

A posting is quarantined if any check flags it: it's stored, not discarded,
so a human can review and release it. Every check runs even after one flags,
so guard_results always has every check's score for the review page.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class Scanner(Protocol):
    """One check. Returns the text for the next check (cleaned or unchanged),
    whether the text passed, and a score for the review page."""

    def scan(self, prompt: str) -> tuple[str, bool, float]: ...


class InvisibleText:
    """Unicode format (Cf), private-use (Co) and unassigned (Cn) characters:
    the categories LLM Guard's InvisibleText strips. Score 1.0 if any were
    found, 0.0 otherwise."""

    _HIDDEN_CATEGORIES = frozenset({"Cf", "Co", "Cn"})

    def scan(self, prompt: str) -> tuple[str, bool, float]:
        cleaned = "".join(
            char for char in prompt if unicodedata.category(char) not in self._HIDDEN_CATEGORIES
        )
        found = cleaned != prompt
        return cleaned, not found, 1.0 if found else 0.0


# The classifier behind PromptInjection, pinned to one commit of its Hugging
# Face repo so an upstream update can't change the guard's behaviour unnoticed.
# To switch to Prompt Guard 2, set "meta-llama/Llama-Prompt-Guard-2-86M" and
# its current commit (gated: accept Meta's license on its Hugging Face page
# and run `hf auth login` first), and check its attack label.
PROMPT_INJECTION_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"
PROMPT_INJECTION_REVISION = "90c9989b1a342275dd0d1a95aad283c04e075671"


class PromptInjection:
    """A Hugging Face text classifier, run on the whole text in overlapping
    512-token chunks: the model reads at most 512 tokens, and real postings
    are often longer. The score is the highest attack probability over the
    chunks; the text is flagged when that's above 0.5, i.e. when the model's
    own top label is the attack label (its default decision, no threshold)."""

    _MAX_TOKENS = 512
    _OVERLAP_TOKENS = 64  # so an attack split across a chunk border is still seen whole

    def __init__(
        self, model: str = PROMPT_INJECTION_MODEL, revision: str = PROMPT_INJECTION_REVISION
    ) -> None:
        self._tokenizer = AutoTokenizer.from_pretrained(model, revision=revision)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model, revision=revision
        ).eval()
        # Class 1 is ProtectAI's INJECTION (class 0 is SAFE). Not yet checked
        # for Prompt Guard 2, whose config couldn't be downloaded.
        self._attack_label = 1

    def scan(self, prompt: str) -> tuple[str, bool, float]:
        chunks = self._tokenizer(
            prompt,
            truncation=True,
            max_length=self._MAX_TOKENS,
            stride=self._OVERLAP_TOKENS,
            return_overflowing_tokens=True,
            padding=True,
            return_tensors="pt",
        )
        chunks.pop("overflow_to_sample_mapping", None)
        with torch.no_grad():
            logits = self._model(**chunks).logits
        attack_probability = logits.softmax(dim=-1)[:, self._attack_label].max().item()
        return prompt, attack_probability <= 0.5, attack_probability


def default_scanners() -> list[Scanner]:
    """The production checks, in order: hidden characters are stripped
    before the classifier reads the text."""
    return [InvisibleText(), PromptInjection()]


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
    """Runs a posting through every check in order, each one's output text
    feeding the next, so `sanitized_text` is the result of the whole chain.

    Detection only: PII redaction is a separate step that runs before this
    (`jobfit.ingest.anonymize`), so the guard only ever sees redacted text.
    """

    def __init__(self, scanners: list[Scanner] | None = None) -> None:
        """`scanners` overrides the default checks, for unit tests that check
        the guard's own logic with fake scanners, without loading any models."""
        self._scanners = scanners if scanners is not None else default_scanners()

    def scan(self, text: str) -> GuardScanResult:
        results = []
        for scanner in self._scanners:
            text, is_valid, score = scanner.scan(text)
            results.append(
                ScannerResult(scanner=type(scanner).__name__, score=score, flagged=not is_valid)
            )
        return GuardScanResult(
            quarantined=any(r.flagged for r in results),
            sanitized_text=text,
            results=results,
        )


@lru_cache(maxsize=1)
def get_guard() -> InjectionGuard:
    """Loads the models once per process; that's the expensive part."""
    return InjectionGuard()

from __future__ import annotations

import hashlib
import re

import numpy as np
from datasketch import MinHash

_NUM_PERM = 128
_SHINGLE_SIZE = 5
_BODY_THRESHOLD = 0.7
_TITLE_THRESHOLD = 0.5
_WORD_RE = re.compile(r"\w+")
_HASHVALUES_DTYPE = MinHash(num_perm=_NUM_PERM).hashvalues.dtype


def content_hash(title: str, company: str, location: str | None = None) -> str:
    """Exact-duplicate key: same title + company + location, case/whitespace-insensitive.

    Location matters: the same title at the same company commonly means
    several distinct open reqs in different cities (e.g. "Technical Account
    Manager" posted separately for Zurich, Geneva, Austin...), not one
    posting duplicated. Without location, those all collapse into one hash.
    """
    normalized_location = (location or "").strip().lower()
    key = f"{title.strip().lower()}|{company.strip().lower()}|{normalized_location}"
    return hashlib.sha256(key.encode()).hexdigest()


def minhash_signature(text: str) -> list[int]:
    """Near-duplicate key over word shingles of the full normalized posting text."""
    words = _WORD_RE.findall(text.lower())
    shingles = {
        " ".join(words[i : i + _SHINGLE_SIZE])
        for i in range(max(len(words) - _SHINGLE_SIZE + 1, 1))
    }
    minhash = MinHash(num_perm=_NUM_PERM)
    for shingle in shingles:
        minhash.update(shingle.encode())
    return [int(v) for v in minhash.hashvalues]


def _title_similarity(title_a: str, title_b: str) -> float:
    words_a = set(_WORD_RE.findall(title_a.lower()))
    words_b = set(_WORD_RE.findall(title_b.lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _body_jaccard(signature_a: list[int], signature_b: list[int]) -> float:
    mh_a, mh_b = MinHash(num_perm=_NUM_PERM), MinHash(num_perm=_NUM_PERM)
    # hashvalues must stay a numpy array of the dtype MinHash itself uses, or
    # the vectorized equality check in jaccard() silently compares garbage.
    mh_a.hashvalues = np.array(signature_a, dtype=_HASHVALUES_DTYPE)
    mh_b.hashvalues = np.array(signature_b, dtype=_HASHVALUES_DTYPE)
    return mh_a.jaccard(mh_b)


def _locations_conflict(location_a: str | None, location_b: str | None) -> bool:
    """True only when both locations are known and clearly different.

    Unknown location (either side) never blocks a match — some sources
    don't report it reliably, and absence isn't evidence of a difference.
    """
    if not location_a or not location_b:
        return False
    return location_a.strip().lower() != location_b.strip().lower()


def is_near_duplicate(
    title_a: str,
    signature_a: list[int],
    title_b: str,
    signature_b: list[int],
    location_a: str | None = None,
    location_b: str | None = None,
    title_threshold: float = _TITLE_THRESHOLD,
    body_threshold: float = _BODY_THRESHOLD,
) -> bool:
    """A posting is a near-duplicate only if the titles are plausibly the same
    role, the locations don't clearly conflict, AND the bodies are highly similar.

    The title gate matters: two different roles at the same company (e.g.
    "Account Executive - EMEA East" vs "Account Executive, Spanish and
    Italian speaker") can share 90%+ of their body text because the shared
    company boilerplate ("who we are", diversity statement, benefits) sits
    at the *top* of the description, ahead of the role-specific content —
    so a body-only check flags them as duplicates. Requiring title overlap
    first avoids that without needing to guess where boilerplate lives.

    The location gate matters just as much: the same title at the same
    company is commonly several distinct open reqs in different cities
    (e.g. "AI Researcher - Post-Training" posted separately for London and
    Bochum, worded almost identically) — genuinely different, both-applicable
    postings, not one posting duplicated. Without this gate they'd collapse
    into one and silently disappear from the shortlist.
    """
    if _title_similarity(title_a, title_b) < title_threshold:
        return False
    if _locations_conflict(location_a, location_b):
        return False
    return _body_jaccard(signature_a, signature_b) >= body_threshold

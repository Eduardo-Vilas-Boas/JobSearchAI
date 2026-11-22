from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable

from datasketch import MinHash

from jobfit.ingest.locations import locations_conflict

_NUM_PERM = 128
_SHINGLE_SIZE = 5
_BODY_THRESHOLD = 0.7
_TITLE_THRESHOLD = 0.5
_WORD_RE = re.compile(r"\w+")

# A line is company boilerplate if it appears in postings for at least this
# many distinct titles, and at least this share of the company's titles.
_BOILERPLATE_MIN_TITLES = 3
_BOILERPLATE_MIN_SHARE = 0.2
# Below this many distinct titles, boilerplate can't be told from content.
_BOILERPLATE_MIN_COMPANY_TITLES = 5
# Fewer words than this left after stripping is too little to compare.
_MIN_BODY_WORDS = 20


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


def boilerplate_lines(postings: Iterable[tuple[str, str]]) -> frozenset[str]:
    """The lines of a company's postings that are its template, not the role:
    "who we are", benefits, diversity statements.

    `postings` is (title, text) for the company's postings. A line counts once
    per distinct title, so a role posted in several cities, or reposted,
    doesn't make its own description look like boilerplate.
    """
    lines_by_title: dict[str, set[str]] = {}
    for title, text in postings:
        lines_by_title.setdefault(_normalize_title(title), set()).update(_lines(text))
    titles = len(lines_by_title)
    if titles < _BOILERPLATE_MIN_COMPANY_TITLES:
        return frozenset()
    threshold = max(_BOILERPLATE_MIN_TITLES, math.ceil(_BOILERPLATE_MIN_SHARE * titles))
    counts = Counter(line for lines in lines_by_title.values() for line in lines)
    return frozenset(line for line, count in counts.items() if count >= threshold)


def body_signature(text: str, boilerplate: frozenset[str]) -> MinHash | None:
    """MinHash over word shingles of a posting with its company's boilerplate
    lines removed, or None when too little is left to compare.

    MinHash uses datasketch's fixed default seed, so signatures are
    comparable across runs; don't pass a custom one.
    """
    body = " ".join(line for line in _lines(text) if line not in boilerplate)
    words = _WORD_RE.findall(body)
    if len(words) < _MIN_BODY_WORDS:
        return None
    minhash = MinHash(num_perm=_NUM_PERM)
    for i in range(len(words) - _SHINGLE_SIZE + 1):
        minhash.update(" ".join(words[i : i + _SHINGLE_SIZE]).encode())
    return minhash


def is_near_duplicate(
    title_a: str,
    signature_a: MinHash | None,
    title_b: str,
    signature_b: MinHash | None,
    location_a: str | None = None,
    location_b: str | None = None,
) -> bool:
    """Two postings of the same company are near-duplicates only if the titles
    are plausibly the same role, the locations don't conflict, AND the bodies
    (boilerplate removed, see `body_signature`) are highly similar.

    The title gate: two different roles at the same company can share most of
    their text through the company template. Stripping the template removes
    most of that; the title check guards what's left (a company with too few
    postings to learn its template from, or template lines that vary).

    The location gate: the same title at the same company is commonly several
    distinct open reqs in different cities, worded almost identically, and
    each is worth applying to. Locations are compared as places (see
    `locations.locations_conflict`): the same set of places, however written
    ("Geneva, Barcelona", "Barcelona; Genève"), or they're different jobs.
    """
    if signature_a is None or signature_b is None:
        return False
    if _title_similarity(title_a, title_b) < _TITLE_THRESHOLD:
        return False
    if locations_conflict(location_a, location_b):
        return False
    return signature_a.jaccard(signature_b) >= _BODY_THRESHOLD


def _lines(text: str) -> list[str]:
    return [" ".join(line.lower().split()) for line in text.splitlines() if line.strip()]


def _normalize_title(title: str) -> str:
    return " ".join(_WORD_RE.findall(title.lower()))


def _title_similarity(title_a: str, title_b: str) -> float:
    words_a = set(_WORD_RE.findall(title_a.lower()))
    words_b = set(_WORD_RE.findall(title_b.lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)

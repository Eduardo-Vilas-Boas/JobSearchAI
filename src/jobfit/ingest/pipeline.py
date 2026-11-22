from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from datasketch import MinHash

from jobfit.config import CompanyConfig
from jobfit.db.models import GuardResult, IngestRun, Posting
from jobfit.db.session import get_session
from jobfit.db.store import (
    find_existing_posting,
    get_or_create_company,
    get_or_create_source,
    iter_canonical_postings,
    mark_closed_postings,
)
from jobfit.ingest.anonymize import Anonymizer, get_anonymizer
from jobfit.ingest.dedup import (
    body_signature,
    boilerplate_lines,
    content_hash,
    is_near_duplicate,
)
from jobfit.ingest.fetchers.base import Fetcher, RawPosting
from jobfit.ingest.fetchers.registry import get_fetcher
from jobfit.ingest.guard import GuardScanResult, InjectionGuard, get_guard
from jobfit.ingest.normalize import detect_language, posting_text


@dataclass
class RunStats:
    fetched: int = 0
    stored: int = 0
    exact_duplicates: int = 0
    near_duplicates: int = 0
    blocked: int = 0
    quarantined: int = 0
    errors: list[str] = field(default_factory=list)


def run_ingest(
    companies: list[CompanyConfig],
    guard: InjectionGuard | None = None,
    anonymizer: Anonymizer | None = None,
    fetchers: Mapping[str, Fetcher] | None = None,
    blocked_companies: Collection[str] = (),
) -> RunStats:
    """Fetches, cleans and stores postings for every configured company.

    Idempotent: re-running with the same postings stores nothing new, since
    each posting is keyed on (source, external_id) before any processing.
    Re-running does update lifecycle dates: last_seen for postings still on
    their board, closed_at for postings that have left it.

    `fetchers` maps an ATS type to the fetcher to use for it; by default
    each company's fetcher comes from the registry (live HTTP).

    Postings whose company is in `blocked_companies` (case and spacing
    ignored) are skipped before any processing and never stored.
    """
    guard = guard or get_guard()
    anonymizer = anonymizer or get_anonymizer()
    stats = RunStats()
    blocked = frozenset(_company_key(name) for name in blocked_companies)

    with get_session() as session:
        ingest_run = IngestRun(started_at=datetime.now(UTC))
        session.add(ingest_run)
        session.flush()

        canonical_postings = iter_canonical_postings(session)

        for company_config in companies:
            try:
                _ingest_company(
                    session,
                    company_config,
                    ingest_run,
                    canonical_postings,
                    guard,
                    anonymizer,
                    fetchers,
                    blocked,
                    stats,
                )
            except Exception as exc:  # noqa: BLE001 - one bad company shouldn't kill the run
                stats.errors.append(f"{company_config.name}: {exc}")

        ingest_run.finished_at = datetime.now(UTC)
        ingest_run.fetched_count = stats.fetched
        ingest_run.stored_count = stats.stored
        ingest_run.duplicate_count = stats.exact_duplicates + stats.near_duplicates
        ingest_run.quarantined_count = stats.quarantined

    return stats


def _ingest_company(
    session,
    company_config: CompanyConfig,
    ingest_run: IngestRun,
    canonical_postings: list[Posting],
    guard: InjectionGuard,
    anonymizer: Anonymizer,
    fetchers: Mapping[str, Fetcher] | None,
    blocked: frozenset[str],
    stats: RunStats,
) -> None:
    if fetchers is None:
        fetcher = get_fetcher(company_config.ats)
    else:
        fetcher = fetchers[company_config.ats]
    raw_postings = fetcher.fetch(company_config.board_token, company_config.name)
    stats.fetched += len(raw_postings)

    company = get_or_create_company(session, company_config.name, company_config.canton_hint)
    source = get_or_create_source(session, company_config.ats)

    # Every posting this run finds on the board gets the same timestamp.
    now = ingest_run.started_at
    new_postings: list[tuple[RawPosting, GuardScanResult]] = []
    for raw in raw_postings:
        if _company_key(raw.company) in blocked:
            stats.blocked += 1
            continue
        existing = find_existing_posting(session, source.id, raw.external_id)
        if existing is not None:
            # Already stored by an earlier run: only its lifecycle dates
            # change, never its text or guard verdict.
            existing.last_seen = now
            existing.closed_at = None  # back on the board, if it had left
            continue
        # PII redacted first, so the guard (and later the LLM) never sees it.
        redacted = anonymizer.anonymize(posting_text(raw.title, raw.description_html))
        new_postings.append((raw, guard.scan(redacted)))

    # Duplicates are only looked for within the company, and its template is
    # learned from all of its postings: stored ones and this run's new ones.
    company_canonicals = [p for p in canonical_postings if p.company_id == company.id]
    boilerplate = boilerplate_lines(
        [(p.title, p.normalized_text) for p in company_canonicals]
        + [(raw.title, scan.sanitized_text) for raw, scan in new_postings]
    )
    signatures = {p.id: body_signature(p.normalized_text, boilerplate) for p in company_canonicals}

    for raw, guard_result in new_postings:
        text = guard_result.sanitized_text  # PII redacted, hidden characters stripped
        signature = body_signature(text, boilerplate)
        hash_key = content_hash(raw.title, raw.company, raw.location)

        duplicate_of = _find_duplicate(
            raw.title, hash_key, signature, raw.location, company_canonicals, signatures
        )
        if duplicate_of is not None:
            stats.exact_duplicates += 1 if duplicate_of.content_hash == hash_key else 0
            stats.near_duplicates += 1 if duplicate_of.content_hash != hash_key else 0

        if guard_result.quarantined:
            stats.quarantined += 1

        posting = Posting(
            source=source,
            company=company,
            external_id=raw.external_id,
            title=raw.title,
            location_raw=raw.location,
            url=raw.url,
            language=detect_language(text),
            normalized_text=text,
            content_hash=hash_key,
            is_quarantined=guard_result.quarantined,
            is_duplicate_of=duplicate_of.id if duplicate_of else None,
            raw_payload=raw.raw_payload,
            posted_at=raw.posted_at,
            last_seen=now,
            ingest_run_id=ingest_run.id,
        )
        session.add(posting)
        session.flush()

        for scanner_result in guard_result.results:
            session.add(
                GuardResult(
                    posting_id=posting.id,
                    scanner=scanner_result.scanner,
                    score=scanner_result.score,
                    flagged=scanner_result.flagged,
                )
            )

        stats.stored += 1

        if duplicate_of is None:
            canonical_postings.append(posting)
            company_canonicals.append(posting)
            signatures[posting.id] = signature

    # Only reached when the fetch succeeded, so a board that fails to load
    # never closes its postings.
    mark_closed_postings(
        session, company.id, source.id, {raw.external_id for raw in raw_postings}, now
    )


def _company_key(name: str) -> str:
    """How company names are matched against the blocklist: case and spacing ignored."""
    return " ".join(name.casefold().split())


def _find_duplicate(
    title: str,
    hash_key: str,
    signature: MinHash | None,
    location: str | None,
    company_canonicals: list[Posting],
    signatures: dict[uuid.UUID, MinHash | None],
) -> Posting | None:
    for existing in company_canonicals:
        if existing.content_hash == hash_key:
            return existing
    for existing in company_canonicals:
        if is_near_duplicate(
            title,
            signature,
            existing.title,
            signatures[existing.id],
            location,
            existing.location_raw,
        ):
            return existing
    return None

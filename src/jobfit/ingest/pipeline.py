from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from jobfit.config import CompanyConfig
from jobfit.db.models import IngestRun, Posting
from jobfit.db.session import get_session
from jobfit.db.store import (
    find_existing_posting,
    get_or_create_company,
    get_or_create_source,
    iter_canonical_postings,
)
from jobfit.ingest.dedup import content_hash, is_near_duplicate, minhash_signature
from jobfit.ingest.fetchers.registry import get_fetcher
from jobfit.ingest.guard import InjectionGuard, get_guard
from jobfit.ingest.normalize import detect_language, html_to_text, normalize_unicode
from jobfit.ingest.redact import redact_pii


@dataclass
class RunStats:
    fetched: int = 0
    stored: int = 0
    exact_duplicates: int = 0
    near_duplicates: int = 0
    quarantined: int = 0
    errors: list[str] = field(default_factory=list)


def run_ingest(companies: list[CompanyConfig], guard: InjectionGuard | None = None) -> RunStats:
    """Fetches, cleans and stores postings for every configured company.

    Idempotent: re-running with the same postings stores nothing new, since
    each posting is keyed on (source, external_id) before any processing.
    """
    guard = guard or get_guard()
    stats = RunStats()

    with get_session() as session:
        ingest_run = IngestRun(started_at=datetime.now(UTC))
        session.add(ingest_run)
        session.flush()

        canonical_postings = iter_canonical_postings(session)

        for company_config in companies:
            try:
                _ingest_company(
                    session, company_config, ingest_run, canonical_postings, guard, stats
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
    stats: RunStats,
) -> None:
    fetcher = get_fetcher(company_config.ats)
    raw_postings = fetcher.fetch(company_config.board_token, company_config.name)
    stats.fetched += len(raw_postings)

    company = get_or_create_company(session, company_config.name, company_config.canton_hint)
    source = get_or_create_source(session, company_config.ats)

    for raw in raw_postings:
        if find_existing_posting(session, source.id, raw.external_id) is not None:
            continue  # already stored by an earlier run — idempotent no-op

        text = redact_pii(normalize_unicode(html_to_text(raw.description_html)))
        full_text_for_hashing = f"{raw.title}\n{text}"
        signature = minhash_signature(full_text_for_hashing)
        hash_key = content_hash(raw.title, raw.company, raw.location)

        duplicate_of = _find_duplicate(
            raw.title, hash_key, signature, raw.location, canonical_postings
        )
        if duplicate_of is not None:
            stats.exact_duplicates += 1 if duplicate_of.content_hash == hash_key else 0
            stats.near_duplicates += 1 if duplicate_of.content_hash != hash_key else 0

        guard_result = guard.scan(f"{raw.title}\n{text}")
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
            minhash_signature=signature,
            is_quarantined=guard_result.quarantined,
            guard_flags=guard_result.flags,
            is_duplicate_of=duplicate_of.id if duplicate_of else None,
            raw_payload=raw.raw_payload,
            posted_at=raw.posted_at,
            ingest_run_id=ingest_run.id,
        )
        session.add(posting)
        session.flush()
        stats.stored += 1

        if duplicate_of is None:
            canonical_postings.append(posting)


def _find_duplicate(
    title: str,
    hash_key: str,
    signature: list[int],
    location: str | None,
    canonical_postings: list[Posting],
) -> Posting | None:
    for existing in canonical_postings:
        if existing.content_hash == hash_key:
            return existing
    for existing in canonical_postings:
        if existing.minhash_signature and is_near_duplicate(
            title,
            signature,
            existing.title,
            existing.minhash_signature,
            location,
            existing.location_raw,
        ):
            return existing
    return None

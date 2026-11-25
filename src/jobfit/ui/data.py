"""Database reads and display helpers shared by the app's pages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from sqlalchemy import select

from jobfit.db.models import Company, GuardResult, Posting, Source
from jobfit.db.session import get_session

# The current guard's scanners, as in guard.default_scanners(); keep in step
# with it. PII redaction is a separate step, not shown here. Postings stored
# before a scanner existed have no score for it (shown blank).
SCANNER_NAMES = ["InvisibleText", "PromptInjection"]


def job_page_link(posting_id: str, title: str) -> str:
    """Link to a posting's own page. The title rides along in the URL so the
    table's link column can show it (and sort by it, hence first); the page
    itself only reads `id`."""
    return f"/job?title={quote_plus(title)}&id={posting_id}"


JOB_LINK_TITLE = r"title=([^&]*)"  # shows the title part of job_page_link()


@st.cache_data(ttl=30)
def load_postings() -> pd.DataFrame:
    with get_session() as session:
        rows = session.execute(
            select(Posting, Company.name)
            .join(Company)
            # Status lives on the canonical posting; duplicates would only
            # repeat it.
            .where(Posting.is_duplicate_of.is_(None))
            .order_by(Posting.posted_at.desc().nulls_last())
        ).all()
        guard_rows = session.execute(
            select(
                GuardResult.posting_id, GuardResult.scanner, GuardResult.score, GuardResult.flagged
            ).order_by(GuardResult.scanner)
        ).all()

    scores_by_posting, flagged_by_posting = _guard_summary(guard_rows)
    records = []
    for posting, company_name in rows:
        record = {
            "id": str(posting.id),
            "title": posting.title,
            "job_page": job_page_link(str(posting.id), posting.title),
            "status": posting.status,
            "company": company_name,
            "location": posting.location_raw,
            # From the ATS: Greenhouse's first_published, Lever's createdAt
            # (when the job was created in Lever, possibly before it went
            # public); for LinkedIn captures, its "N days ago" at capture time.
            "posted": posting.posted_at,
            "last_seen": posting.last_seen,
            "closed_at": posting.closed_at,
            "url": posting.url,
            "verdict": "quarantined" if posting.is_quarantined else "allowed",
            # The verdict was decided at ingest and isn't recomputed, so it
            # can come from a scanner since removed (e.g. Anonymize or
            # Language); this column shows which ones decided it.
            "flagged_by": ", ".join(flagged_by_posting.get(posting.id, [])),
        }
        scanner_scores = scores_by_posting.get(posting.id, {})
        for name in SCANNER_NAMES:
            record[name] = scanner_scores.get(name)
        records.append(record)

    return pd.DataFrame.from_records(records, index="id")


@dataclass(frozen=True)
class Copy:
    """Another stored copy of a posting: a duplicate found at ingest."""

    source: str
    url: str


@dataclass(frozen=True)
class JobDetails:
    id: uuid.UUID
    title: str
    company: str
    location: str | None
    source: str
    url: str
    status: str
    status_changed_at: object
    posted_at: object
    first_seen: object
    last_seen: object
    closed_at: object
    language: str | None
    text: str
    quarantined: bool
    scores: dict[str, float]
    flagged_by: list[str]
    duplicate_of: uuid.UUID | None
    copies: list[Copy]


def load_job(posting_id: uuid.UUID) -> JobDetails | None:
    """Not cached: the page shows the status just saved."""
    with get_session() as session:
        posting = session.get(Posting, posting_id)
        if posting is None:
            return None
        guard_rows = session.execute(
            select(GuardResult.scanner, GuardResult.score, GuardResult.flagged)
            .where(GuardResult.posting_id == posting_id)
            .order_by(GuardResult.scanner)
        ).all()
        copies = session.execute(
            select(Source.name, Posting.url)
            .join(Source)
            .where(Posting.is_duplicate_of == posting_id)
            .order_by(Posting.first_seen)
        ).all()
        return JobDetails(
            id=posting.id,
            title=posting.title,
            company=posting.company.name,
            location=posting.location_raw,
            source=posting.source.name,
            url=posting.url,
            status=posting.status,
            status_changed_at=posting.status_changed_at,
            posted_at=posting.posted_at,
            first_seen=posting.first_seen,
            last_seen=posting.last_seen,
            closed_at=posting.closed_at,
            language=posting.language,
            text=posting.normalized_text,
            quarantined=posting.is_quarantined,
            scores={scanner: score for scanner, score, _ in guard_rows},
            flagged_by=[scanner for scanner, _, flagged in guard_rows if flagged],
            duplicate_of=posting.is_duplicate_of,
            copies=[Copy(source, url) for source, url in copies],
        )


def _guard_summary(guard_rows) -> tuple[dict, dict]:
    scores_by_posting: dict = {}
    flagged_by_posting: dict = {}
    for posting_id, scanner, score, flagged in guard_rows:
        scores_by_posting.setdefault(posting_id, {})[scanner] = score
        if flagged:
            flagged_by_posting.setdefault(posting_id, []).append(scanner)
    return scores_by_posting, flagged_by_posting


def status_label(status: str) -> str:
    return status.replace("_", " ")


def date_or(value, missing: str) -> str:
    return f"{value:%Y-%m-%d}" if pd.notna(value) else missing

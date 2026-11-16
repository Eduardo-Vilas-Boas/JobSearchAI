from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobfit.db.models import Company, Posting, Source


def get_or_create_company(session: Session, name: str, canton_hint: str | None = None) -> Company:
    company = session.scalar(select(Company).where(Company.name == name))
    if company is None:
        company = Company(name=name, canton_hint=canton_hint)
        session.add(company)
        session.flush()
    return company


def get_or_create_source(session: Session, name: str) -> Source:
    source = session.scalar(select(Source).where(Source.name == name))
    if source is None:
        source = Source(name=name)
        session.add(source)
        session.flush()
    return source


def find_existing_posting(session: Session, source_id, external_id: str) -> Posting | None:
    return session.scalar(
        select(Posting).where(Posting.source_id == source_id, Posting.external_id == external_id)
    )


def iter_canonical_postings(session: Session) -> list[Posting]:
    """Postings not already marked as a duplicate of another — the set a new
    posting's MinHash signature gets compared against for near-dup detection.

    Ordered by first_seen so that, when a new posting matches more than one
    existing candidate, the earliest one deterministically wins as canonical
    — without this, Postgres gives no row-order guarantee and the winner
    could differ between runs.
    """
    query = select(Posting).where(Posting.is_duplicate_of.is_(None)).order_by(Posting.first_seen)
    return list(session.scalars(query))

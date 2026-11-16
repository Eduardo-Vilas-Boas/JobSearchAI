from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(unique=True)
    canton_hint: Mapped[str | None]

    postings: Mapped[list[Posting]] = relationship(back_populates="company")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(unique=True)  # e.g. "greenhouse", "lever"

    postings: Mapped[list[Posting]] = relationship(back_populates="source")


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(default=0)
    stored_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    quarantined_count: Mapped[int] = mapped_column(default=0)


class Posting(Base):
    __tablename__ = "postings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_posting_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    source: Mapped[Source] = relationship(back_populates="postings")

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    company: Mapped[Company] = relationship(back_populates="postings")

    external_id: Mapped[str]
    title: Mapped[str]
    location_raw: Mapped[str | None]
    url: Mapped[str]
    language: Mapped[str | None]

    normalized_text: Mapped[str]
    # exact-dup key: hash(title + company + location)
    content_hash: Mapped[str] = mapped_column(index=True)
    minhash_signature: Mapped[list[int] | None] = mapped_column(JSON)  # near-dup key

    is_quarantined: Mapped[bool] = mapped_column(default=False)
    guard_flags: Mapped[list[str] | None] = mapped_column(JSON)

    is_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("postings.id"))

    raw_payload: Mapped[dict] = mapped_column(JSON)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingest_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingest_runs.id"))

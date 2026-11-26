"""Local HTTP endpoint the Chrome extension (`extension/`) posts captured
pages to. Run with `uv run python -m jobfit.ingest.capture.server`; it
listens on 127.0.0.1 only.

Any website open in the browser can also send requests to localhost, so
only requests from a Chrome extension's origin are accepted. Requests must
be JSON, which a website can't send cross-origin without a CORS preflight,
and the server allows no cross-origin requests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from jobfit.config import load_blocked_companies
from jobfit.db.models import Posting, Source
from jobfit.db.session import get_session
from jobfit.ingest.anonymize import Anonymizer
from jobfit.ingest.capture import NotAJobPosting, UnsupportedSite, parse_capture
from jobfit.ingest.fetchers.base import RawPosting
from jobfit.ingest.guard import InjectionGuard
from jobfit.ingest.normalize import html_to_text
from jobfit.ingest.pipeline import CaptureStatus, ingest_capture

HOST = "127.0.0.1"
PORT = 8765
_EXTENSION_ORIGIN = "chrome-extension://"


class CaptureRequest(BaseModel):
    url: str
    html: str


class PreviewResponse(BaseModel):
    """What the parser read from the page, before anything is stored.

    `description` is the text before PII redaction, which happens on save."""

    source: str
    external_id: str
    title: str
    company: str
    location: str | None
    posted_at: datetime | None
    url: str
    description: str
    description_chars: int
    already_stored: bool


class CaptureResponse(BaseModel):
    status: CaptureStatus
    title: str
    company: str
    location: str | None
    posted_at: datetime | None
    url: str
    quarantined: bool
    duplicate: bool


def create_app(
    guard: InjectionGuard | None = None, anonymizer: Anonymizer | None = None
) -> FastAPI:
    """`guard` and `anonymizer` default to the real ones, loaded on the
    first capture (the guard's model takes a few seconds)."""
    app = FastAPI(title="jobfit capture")

    @app.post("/previews")
    def preview(body: CaptureRequest, request: Request) -> PreviewResponse:
        raw = _parse(body, request)
        description = html_to_text(raw.description_html)
        return PreviewResponse(
            source=raw.source,
            external_id=raw.external_id,
            title=raw.title,
            company=raw.company,
            location=raw.location,
            posted_at=raw.posted_at,
            url=raw.url,
            description=description,
            description_chars=len(description),
            already_stored=_is_stored(raw),
        )

    @app.post("/captures")
    def capture(body: CaptureRequest, request: Request) -> CaptureResponse:
        raw = _parse(body, request)
        result = ingest_capture(
            raw, guard=guard, anonymizer=anonymizer, blocked_companies=load_blocked_companies()
        )
        return CaptureResponse(
            status=result.status,
            title=raw.title,
            company=raw.company,
            location=raw.location,
            posted_at=raw.posted_at,
            url=raw.url,
            quarantined=result.quarantined,
            duplicate=result.duplicate_of is not None,
        )

    return app


def _is_stored(raw: RawPosting) -> bool:
    with get_session() as session:
        return (
            session.scalar(
                select(Posting.id)
                .join(Source)
                .where(Source.name == raw.source, Posting.external_id == raw.external_id)
            )
            is not None
        )


def _parse(body: CaptureRequest, request: Request) -> RawPosting:
    if not request.headers.get("origin", "").startswith(_EXTENSION_ORIGIN):
        raise HTTPException(403, "only the jobfit browser extension may post captures")
    try:
        return parse_capture(body.html, body.url, datetime.now(UTC))
    except (NotAJobPosting, UnsupportedSite) as exc:
        raise HTTPException(422, str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host=HOST, port=PORT)

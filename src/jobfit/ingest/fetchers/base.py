from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RawPosting:
    """One posting exactly as returned by an ATS, before any normalization."""

    source: str
    external_id: str
    company: str
    title: str
    location: str | None
    description_html: str
    raw_payload: dict
    posted_at: datetime | None
    url: str


class Fetcher(Protocol):
    """Pulls the current postings for one company from its ATS."""

    def fetch(self, board_token: str, company: str) -> list[RawPosting]: ...

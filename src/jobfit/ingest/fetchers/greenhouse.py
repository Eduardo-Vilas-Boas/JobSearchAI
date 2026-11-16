from __future__ import annotations

from datetime import datetime

import httpx

from jobfit.ingest.fetchers.base import RawPosting

API_BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseFetcher:
    """Fetches postings from a company's public Greenhouse job board.

    This is the same unauthenticated endpoint Greenhouse customers embed
    on their own careers page (https://developers.greenhouse.io/job-board.html).
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=15.0)

    def fetch(self, board_token: str, company: str) -> list[RawPosting]:
        response = self._client.get(f"{API_BASE}/{board_token}/jobs", params={"content": "true"})
        response.raise_for_status()
        jobs = response.json()["jobs"]
        return [self._to_raw_posting(job, company) for job in jobs]

    @staticmethod
    def _to_raw_posting(job: dict, company: str) -> RawPosting:
        posted_at = None
        if job.get("first_published"):
            posted_at = datetime.fromisoformat(job["first_published"])
        return RawPosting(
            source="greenhouse",
            external_id=str(job["id"]),
            company=company,
            title=job["title"],
            location=(job.get("location") or {}).get("name"),
            description_html=job.get("content") or "",
            raw_payload=job,
            posted_at=posted_at,
            url=job["absolute_url"],
        )

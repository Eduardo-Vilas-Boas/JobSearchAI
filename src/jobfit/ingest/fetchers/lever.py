from __future__ import annotations

from datetime import UTC, datetime

import httpx

from jobfit.ingest.fetchers.base import RawPosting

API_BASE = "https://api.lever.co/v0/postings"


class LeverFetcher:
    """Fetches postings from a company's public Lever job board.

    Same unauthenticated JSON endpoint Lever customers embed on their own
    careers page (https://github.com/lever/postings-api).
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=15.0)

    def fetch(self, board_token: str, company: str) -> list[RawPosting]:
        response = self._client.get(f"{API_BASE}/{board_token}", params={"mode": "json"})
        response.raise_for_status()
        postings = response.json()
        return [self._to_raw_posting(posting, company) for posting in postings]

    @staticmethod
    def _to_raw_posting(posting: dict, company: str) -> RawPosting:
        posted_at = None
        if posting.get("createdAt"):
            posted_at = datetime.fromtimestamp(posting["createdAt"] / 1000, tz=UTC)
        return RawPosting(
            source="lever",
            external_id=posting["id"],
            company=company,
            title=posting["text"],
            location=", ".join((posting.get("categories") or {}).get("allLocations") or []) or None,
            description_html=_description_html(posting),
            raw_payload=posting,
            posted_at=posted_at,
            url=posting["hostedUrl"],
        )


def _description_html(posting: dict) -> str:
    """The whole posting body, as the careers page shows it.

    Lever splits it into `description` (often only the company intro),
    `lists` (headed sections such as responsibilities and requirements, each
    `content` a run of <li> items) and `additional` (closing text). The role
    is mostly in the last two, so all three are joined, in page order.
    """
    parts = [posting.get("description") or ""]
    for section in posting.get("lists") or []:
        parts.append(f"<h3>{section.get('text') or ''}</h3><ul>{section.get('content') or ''}</ul>")
    parts.append(posting.get("additional") or "")
    return "\n".join(part for part in parts if part)

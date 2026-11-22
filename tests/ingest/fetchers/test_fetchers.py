"""Fetcher mapping checks against real recorded ATS responses.

Expected values are copied by hand from tests/fixtures/, not read back
through the same keys the fetcher uses, so a wrong mapping fails here. These
can't catch the ATS changing its format; test_fetchers_live.py does that.
"""

from datetime import UTC, datetime
from pathlib import Path

import httpx

from jobfit.ingest.fetchers.greenhouse import GreenhouseFetcher
from jobfit.ingest.fetchers.lever import LeverFetcher

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _client_serving(fixture: str) -> httpx.Client:
    body = (FIXTURES / fixture).read_bytes()
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)))


def test_greenhouse_fetcher_maps_recorded_response():
    postings = GreenhouseFetcher(_client_serving("greenhouse_scandit.json")).fetch(
        "scandit", "Scandit"
    )

    assert [p.title for p in postings] == [
        "Accounts Payable (A/P) Specialist (6-Month Fixed-Term Contract)",
        "Business Development Representative - French Speaker",
    ]
    first = postings[0]
    assert (first.source, first.company, first.location) == ("greenhouse", "Scandit", "Warsaw")
    assert first.posted_at == datetime.fromisoformat("2026-09-28T04:23:26-04:00")
    assert first.url.startswith("https://")
    assert first.description_html


def test_lever_fetcher_maps_recorded_response():
    postings = LeverFetcher(_client_serving("lever_sonarsource.json")).fetch(
        "sonarsource", "SonarSource"
    )

    assert [p.title for p in postings] == [
        "Account Executive - EMEA East",
        "Account Executive (Spanish and Italian speaker)",
    ]
    first = postings[0]
    assert (first.source, first.company, first.location) == ("lever", "SonarSource", "Geneva")
    # Lever's createdAt is epoch milliseconds.
    assert first.posted_at == datetime.fromtimestamp(1793102018.254, tz=UTC)
    assert first.url.startswith("https://")
    assert first.description_html

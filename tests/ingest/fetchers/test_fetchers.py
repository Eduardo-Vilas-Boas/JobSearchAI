import json
from pathlib import Path

import httpx
import respx

from jobfit.ingest.fetchers.greenhouse import GreenhouseFetcher
from jobfit.ingest.fetchers.lever import LeverFetcher

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


@respx.mock
def test_greenhouse_fetcher_parses_real_response_shape():
    payload = json.loads((FIXTURES / "greenhouse_scandit.json").read_text())
    respx.get("https://boards-api.greenhouse.io/v1/boards/scandit/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )

    postings = GreenhouseFetcher().fetch("scandit", "Scandit")

    assert len(postings) == len(payload["jobs"])
    first = postings[0]
    assert first.source == "greenhouse"
    assert first.company == "Scandit"
    assert first.external_id == str(payload["jobs"][0]["id"])
    assert first.title == payload["jobs"][0]["title"]
    assert first.url == payload["jobs"][0]["absolute_url"]
    assert first.posted_at is not None
    assert first.description_html == payload["jobs"][0]["content"]
    assert first.location == payload["jobs"][0]["location"]["name"]


@respx.mock
def test_lever_fetcher_parses_real_response_shape():
    payload = json.loads((FIXTURES / "lever_sonarsource.json").read_text())
    respx.get("https://api.lever.co/v0/postings/sonarsource").mock(
        return_value=httpx.Response(200, json=payload)
    )

    postings = LeverFetcher().fetch("sonarsource", "SonarSource")

    assert len(postings) == len(payload)
    first = postings[0]
    assert first.source == "lever"
    assert first.company == "SonarSource"
    assert first.external_id == payload[0]["id"]
    assert first.title == payload[0]["text"]
    assert first.url == payload[0]["hostedUrl"]
    assert first.posted_at is not None
    assert first.description_html == payload[0]["description"]
    assert first.location == ", ".join(payload[0]["categories"]["allLocations"])


@respx.mock
def test_greenhouse_fetcher_raises_on_http_error():
    respx.get("https://boards-api.greenhouse.io/v1/boards/missing/jobs").mock(
        return_value=httpx.Response(404)
    )

    try:
        GreenhouseFetcher().fetch("missing", "Nobody")
        raised = False
    except httpx.HTTPStatusError:
        raised = True

    assert raised

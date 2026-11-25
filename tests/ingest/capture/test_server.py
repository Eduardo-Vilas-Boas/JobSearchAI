"""The local endpoint the browser extension posts captured pages to.

Runs against the test database, with the real InjectionGuard over a fake
scanner (no models loaded) and a pass-through anonymizer.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobfit.ingest.capture.server import create_app
from jobfit.ingest.guard import InjectionGuard
from tests.fakes import FakeAnonymizer, fake_scanner

FIXTURE = Path(__file__).parents[2] / "fixtures" / "linkedin_job_search.html"
JOB_URL = "https://www.linkedin.com/jobs/search/?currentJobId=4000000001"
EXTENSION = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}


@pytest.fixture
def client(clean_db):  # pylint: disable=unused-argument
    app = create_app(guard=InjectionGuard([fake_scanner("Scanner")]), anonymizer=FakeAnonymizer())
    return TestClient(app)


def _post(client, url=JOB_URL, html=None, headers=EXTENSION):
    return client.post(
        "/captures", json={"url": url, "html": html or FIXTURE.read_text()}, headers=headers
    )


def test_a_captured_job_page_is_stored_and_described_back(client):
    response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stored"
    assert (body["title"], body["company"], body["location"]) == (
        "Perception Engineer",
        "Example Robotics",
        "Zurich, Switzerland",
    )
    assert body["quarantined"] is False
    assert body["duplicate"] is False


def test_a_preview_reads_the_page_without_storing_it(client):
    response = client.post(
        "/previews", json={"url": JOB_URL, "html": FIXTURE.read_text()}, headers=EXTENSION
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Perception Engineer"
    assert response.json()["description_chars"] > 0
    assert _post(client).json()["status"] == "stored"  # the preview stored nothing


def test_capturing_twice_says_it_was_already_stored(client):
    _post(client)

    assert _post(client).json()["status"] == "already_stored"


def test_requests_not_from_the_extension_are_refused(client):
    """Any website open in the browser can send requests to localhost; only
    the extension's own origin is accepted."""
    assert _post(client, headers={"Origin": "https://example.com"}).status_code == 403
    assert _post(client, headers={}).status_code == 403


def test_a_page_without_a_job_is_rejected(client):
    response = _post(client, url="https://www.linkedin.com/feed/", html="<html><body/></html>")

    assert response.status_code == 422
    assert "job" in response.json()["detail"].lower()


def test_a_site_without_a_parser_is_rejected(client):
    response = _post(client, url="https://www.example.com/careers/1")

    assert response.status_code == 422

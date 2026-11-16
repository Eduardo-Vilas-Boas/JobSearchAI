import json
from pathlib import Path

import httpx
import respx
from sqlalchemy import select

from jobfit.config import CompanyConfig
from jobfit.db.models import Posting
from jobfit.db.session import get_session
from jobfit.ingest.guard import GuardResult, InjectionGuard
from jobfit.ingest.pipeline import run_ingest

FIXTURES = Path(__file__).parent.parent / "fixtures"

COMPANIES = [
    CompanyConfig(name="Scandit", ats="greenhouse", board_token="scandit"),
    CompanyConfig(name="SonarSource", ats="lever", board_token="sonarsource"),
]


class _FakeGuard(InjectionGuard):
    """Skips loading the real scanner model — guard.py has its own tests."""

    def __init__(self) -> None:
        pass

    def scan(self, text: str) -> GuardResult:  # noqa: ARG002
        return GuardResult(quarantined=False, risk_score=-1.0, flags=[])


def _mock_ats_endpoints():
    gh_payload = json.loads((FIXTURES / "greenhouse_scandit.json").read_text())
    lever_payload = json.loads((FIXTURES / "lever_sonarsource.json").read_text())
    respx.get("https://boards-api.greenhouse.io/v1/boards/scandit/jobs").mock(
        return_value=httpx.Response(200, json=gh_payload)
    )
    respx.get("https://api.lever.co/v0/postings/sonarsource").mock(
        return_value=httpx.Response(200, json=lever_payload)
    )
    return gh_payload, lever_payload


@respx.mock
def test_run_ingest_stores_postings_from_both_ats_types(clean_db):
    gh_payload, lever_payload = _mock_ats_endpoints()

    stats = run_ingest(COMPANIES, guard=_FakeGuard())

    expected_count = len(gh_payload["jobs"]) + len(lever_payload)
    assert stats.fetched == expected_count
    assert stats.stored == expected_count
    assert stats.exact_duplicates == 0

    with get_session() as session:
        stored = session.scalars(select(Posting)).all()
        assert len(stored) == expected_count


@respx.mock
def test_run_ingest_is_idempotent_on_rerun(clean_db):
    _mock_ats_endpoints()

    first = run_ingest(COMPANIES, guard=_FakeGuard())
    second = run_ingest(COMPANIES, guard=_FakeGuard())

    assert second.stored == 0  # every posting already existed, by (source, external_id)

    with get_session() as session:
        stored = session.scalars(select(Posting)).all()
        assert len(stored) == first.stored


@respx.mock
def test_run_ingest_flags_near_duplicate_across_companies(clean_db):
    gh_payload, lever_payload = _mock_ats_endpoints()
    # Repost the same Greenhouse job under a different company/source, with a
    # trivial wording tweak and one appended sentence — a classic cross-board repost.
    reposted_job = dict(gh_payload["jobs"][0])
    reposted_job["id"] = 999999999
    reposted_job["content"] = reposted_job["content"].replace("Specialist", "Specialist II")
    reposted_job["content"] += " We are an equal opportunity employer."
    respx.get("https://boards-api.greenhouse.io/v1/boards/squirro/jobs").mock(
        return_value=httpx.Response(200, json={"jobs": [reposted_job], "meta": gh_payload["meta"]})
    )
    companies = [*COMPANIES, CompanyConfig(name="Squirro", ats="greenhouse", board_token="squirro")]

    stats = run_ingest(companies, guard=_FakeGuard())

    assert stats.near_duplicates == 1

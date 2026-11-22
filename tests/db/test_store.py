"""Tests for setting a job's status, against the local Postgres."""

import pytest
from sqlalchemy import select

from jobfit.config import CompanyConfig
from jobfit.db.models import Posting
from jobfit.db.session import get_session
from jobfit.db.store import set_status
from jobfit.ingest.guard import InjectionGuard
from jobfit.ingest.pipeline import run_ingest
from tests.fakes import FakeAnonymizer, FakeFetcher, fake_scanner, raw_posting


@pytest.fixture
def posting_id(clean_db):  # pylint: disable=unused-argument
    run_ingest(
        [CompanyConfig(name="Acme", ats="greenhouse", board_token="acme")],
        guard=InjectionGuard([fake_scanner("Scanner")]),
        anonymizer=FakeAnonymizer(),
        fetchers={"greenhouse": FakeFetcher({"acme": [raw_posting("a1")]})},
    )
    with get_session() as session:
        return session.scalar(select(Posting.id))


def _status(posting_id):
    with get_session() as session:
        posting = session.get_one(Posting, posting_id)
        return posting.status, posting.status_changed_at


def test_any_status_can_follow_any_other(posting_id):  # pylint: disable=redefined-outer-name
    for status in ["interviewing", "new", "closed", "applied"]:
        with get_session() as session:
            set_status(session, posting_id, status)
        assert _status(posting_id)[0] == status


def test_changing_status_records_when(posting_id):  # pylint: disable=redefined-outer-name
    with get_session() as session:
        set_status(session, posting_id, "applied")
    first_change = _status(posting_id)[1]

    with get_session() as session:
        set_status(session, posting_id, "interviewing")

    assert first_change is not None and _status(posting_id)[1] > first_change


def test_unknown_status_is_rejected(posting_id):  # pylint: disable=redefined-outer-name
    with pytest.raises(ValueError), get_session() as session:
        set_status(session, posting_id, "ghosted")
    assert _status(posting_id)[0] == "new"

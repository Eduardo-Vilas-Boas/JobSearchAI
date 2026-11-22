"""Live smoke test: each fetcher against one real board from companies.yaml.

The only test that notices an ATS changing its response format. Skipped by
default (network, and boards change daily); run with `uv run pytest -m live`.
Asserts properties every posting must have, not specific postings.
"""

import pytest

from jobfit.config import load_companies
from jobfit.ingest.fetchers.registry import FETCHERS, get_fetcher

pytestmark = pytest.mark.live


def _one_company_per_ats():
    companies = {}
    for company in load_companies():
        companies.setdefault(company.ats, company)
    return [companies[ats] for ats in FETCHERS if ats in companies]


@pytest.mark.parametrize("company", _one_company_per_ats(), ids=lambda c: f"{c.ats}-{c.name}")
def test_fetcher_returns_complete_postings_from_live_board(company):
    postings = get_fetcher(company.ats).fetch(company.board_token, company.name)

    assert postings, f"{company.name}'s board returned no postings"
    for p in postings:
        assert p.source == company.ats
        assert p.external_id and p.title and p.description_html
        assert p.url.startswith("https://")
    assert len({p.external_id for p in postings}) == len(postings)
    assert any(p.posted_at is not None for p in postings)

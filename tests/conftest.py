import pytest
from sqlalchemy import text

from jobfit.db.session import get_session


@pytest.fixture
def clean_db():
    """Truncates all jobfit tables so DB-backed tests start from empty state.

    Requires a running local Postgres (see docker-compose.yml) — these tests
    are not run as part of the no-network, no-DB unit test suite.
    """
    with get_session() as session:
        session.execute(
            text("TRUNCATE postings, ingest_runs, companies, sources RESTART IDENTITY CASCADE")
        )
    yield

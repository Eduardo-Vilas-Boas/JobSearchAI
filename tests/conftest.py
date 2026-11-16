import os

import pytest
from sqlalchemy import create_engine, make_url, text

import jobfit.config
from jobfit.config import REPO_ROOT, Settings

# Tests get their own database (`<dev db>_test`, in the same Postgres container)
# so `clean_db`'s TRUNCATE can never wipe postings the real CLI ingested. This
# must run before anything imports `jobfit.db.session`, which builds its engine
# from `jobfit.config.settings` at import time — conftest is imported before
# any test module, so rebinding the module-level `settings` here is enough.
_DEV_URL = make_url(Settings().database_url)
_TEST_URL = _DEV_URL.set(database=f"{_DEV_URL.database}_test")
os.environ["JOBFIT_DATABASE_URL"] = _TEST_URL.render_as_string(hide_password=False)
jobfit.config.settings = Settings()


@pytest.fixture(scope="session")
def test_database() -> None:
    """Creates the test database if missing and migrates it to head.

    Done here rather than in a docker-entrypoint-initdb.d script because those
    only run on an empty volume — an existing dev volume would never get it.
    """
    from alembic.config import Config

    from alembic import command

    admin = create_engine(_DEV_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": _TEST_URL.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_TEST_URL.database}"'))
    admin.dispose()

    # No config file passed, so alembic/env.py skips fileConfig() and leaves
    # pytest's logging setup alone; env.py picks the URL up from the rebound
    # `jobfit.config.settings`.
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def clean_db(test_database):  # pylint: disable=redefined-outer-name,unused-argument
    """Truncates all jobfit tables so DB-backed tests start from empty state.

    Requires a running local Postgres (see docker-compose.yml). Refuses to run
    against any database whose name doesn't end in `_test` — a last line of
    defence against the redirect above ever silently failing.
    """
    from jobfit.db.session import get_session

    with get_session() as session:
        current = session.execute(text("SELECT current_database()")).scalar()
        if not current.endswith("_test"):
            raise RuntimeError(f"clean_db refusing to TRUNCATE non-test database {current!r}")
        session.execute(
            text(
                "TRUNCATE guard_results, postings, ingest_runs, companies, sources "
                "RESTART IDENTITY CASCADE"
            )
        )

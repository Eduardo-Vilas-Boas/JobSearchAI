import os

import pytest
from sqlalchemy import create_engine, make_url, text

import jobfit.config
from jobfit.config import REPO_ROOT, Settings

# Tests get their own database, `jobfit_test`, in the local Postgres container
# from docker-compose.yml (same credentials), so `clean_db`'s TRUNCATE can
# never wipe postings the real CLI ingested. Set here, not read from `.env`,
# so the tests never depend on the database the CLI uses.
#
# This must run before anything imports `jobfit.db.session`, which builds its
# engine from `jobfit.config.settings` at import time. Conftest is imported
# before any test module, so rebinding the module-level `settings` is enough.
_TEST_URL = make_url("postgresql+psycopg://jobfit:jobfit@localhost:5432/jobfit_test")
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

    # CREATE DATABASE needs a connection to a database that already exists;
    # `postgres` is the maintenance database every Postgres server has.
    admin = create_engine(_TEST_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
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

    Requires a running local Postgres (see docker-compose.yml). First checks
    that the code under test is connected to the test database, in case the
    redirect above ever silently fails; then truncates over its own
    connection, which can only reach the test database.
    """
    from jobfit.db.session import get_session

    with get_session() as session:
        current = session.execute(text("SELECT current_database()")).scalar()
    if current != _TEST_URL.database:
        raise RuntimeError(f"app is connected to {current!r}, not the test database")

    engine = create_engine(_TEST_URL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE guard_results, postings, ingest_runs, companies, sources "
                    "RESTART IDENTITY CASCADE"
                )
            )
    finally:
        engine.dispose()

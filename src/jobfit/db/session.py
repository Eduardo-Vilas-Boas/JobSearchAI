from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobfit.config import settings

_engine = create_engine(settings.database_url)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

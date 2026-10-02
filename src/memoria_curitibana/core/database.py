"""Database engine and session factories, built on first use."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from memoria_curitibana.core.config import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Builds the engine lazily, so importing this module never needs a live database."""
    return create_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Returns the process-wide session factory bound to the application engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def create_session() -> Session:
    """Opens a new session bound to the application engine."""
    return get_session_factory()()


@contextmanager
def get_db() -> Iterator[Session]:
    """
    Hands a session to scripts and workers that own their own transaction.

    The caller decides when to commit; the session is always closed here.
    """
    db = create_session()
    try:
        yield db
    finally:
        db.close()

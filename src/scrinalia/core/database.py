"""Database engine and session factories, built on first use."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from types import TracebackType
from typing import Protocol

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from scrinalia.core.config import settings


class SessionContext(Protocol):
    """A session that can be opened with ``with`` — the shape ``create_session`` returns."""

    def __enter__(self) -> Session:
        raise NotImplementedError

    # The signature is the standard context-manager protocol's, argument by argument, and every
    # detail is load-bearing. ``bool | None`` is what every ``@contextmanager`` returns. The
    # parameters are *contravariant*, so declaring them ``Any`` looks permissive but rejects the very
    # generators this codebase hands it. And they are **positional-only**, exactly as typeshed
    # declares ``AbstractContextManager.__exit__``: without the ``/`` a protocol match also compares
    # parameter *names*, and ``typ`` against an implementation's ``type_`` is a mismatch pyright
    # reports as an incompatible ``__exit__``.
    def __exit__(
        self,
        typ: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> bool | None:
        raise NotImplementedError


#: What a writer takes so a test can hand it the test's own session. Two ledgers share it — the
#: worker execution ledger and the API failure ledger — which is why it lives here and not in either.
SessionFactory = Callable[[], SessionContext]


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


def runner_database_url() -> str:
    """
    The DSN the external runner connects with.

    ``RUNNER_DATABASE_URL`` when set, ``DATABASE_URL`` otherwise. The split is the hardening ADR
    0014 documents: a GPU host can hold a least-privilege role and its own TLS parameters without
    the API's credential. Read at call time, so a test can isolate the configuration.
    """
    if settings.RUNNER_DATABASE_URL is not None:
        return settings.RUNNER_DATABASE_URL.get_secret_value()
    return settings.DATABASE_URL


@lru_cache(maxsize=1)
def get_runner_engine() -> Engine:
    """The runner's own engine: a separate pool from the API's, built only by the runner process."""
    return create_engine(runner_database_url(), echo=False, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_runner_session_factory() -> sessionmaker[Session]:
    """Returns the runner's session factory, bound to its own engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=get_runner_engine())


def create_runner_session() -> Session:
    """Opens a session for the external runner: its own DSN, its own pool, its own cache entries."""
    return get_runner_session_factory()()


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

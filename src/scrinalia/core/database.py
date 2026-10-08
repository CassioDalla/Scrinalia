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

    def __enter__(self) -> Session: ...

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
    ) -> bool | None: ...


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

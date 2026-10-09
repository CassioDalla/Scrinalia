"""The first-run write against two real connections: the guarantee the HTTP suite cannot see.

The route's atomicity is a **table lock**, and a lock only exists between two transactions that really
run at once. The suite's ``api_client`` deliberately shares the test's single transaction — that is
what makes the HTTP tests fast, and it is also why they cannot show this — so this file opens its own
sessions on the ``engine``, commits for real, and removes what it wrote by hand.

The measurement it pins is the one ADR 0011 records: ``INSERT … SELECT … WHERE NOT EXISTS`` alone
lets both calls insert, and taking ``LOCK TABLE auth_users IN EXCLUSIVE MODE`` first is what makes the
second one wait, see the committed row, and insert nothing.
"""

from __future__ import annotations

import threading

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from scrinalia.domains.identity.models import AuthUser
from scrinalia.domains.identity.repository.user_repo import UserRepository

FIRST = "primeiro@instituicao.org"
SECOND = "segundo@instituicao.org"

#: How long the second call is given to prove it is *waiting* rather than finished. It is a positive
#: wait — the thread has already announced that it is about to call — so the test fails only when the
#: lock was not taken, which is the defect it exists to catch.
BLOCKED_PATIENCE_SECONDS = 0.5


def _count(engine: Engine) -> int:
    with Session(bind=engine) as db:
        return int(db.scalar(select(func.count()).select_from(AuthUser)) or 0)


def _remove_what_this_file_wrote(engine: Engine) -> None:
    """
    Deletes the two addresses by hand.

    These rows are **committed**, so unlike every other fixture's work the test teardown cannot roll
    them back, and "``auth_users`` is empty" is exactly what the first-run tests assert.
    """
    with Session(bind=engine) as cleanup:
        cleanup.execute(delete(AuthUser).where(AuthUser.email.in_([FIRST, SECOND])))
        cleanup.commit()


def test_a_second_concurrent_call_creates_nothing(engine: Engine) -> None:
    reached = threading.Event()
    outcomes: list[AuthUser | None] = []
    worker: threading.Thread | None = None
    first = Session(bind=engine)
    try:
        assert UserRepository(first).create_first_admin(email=FIRST, name="Primeiro", password_hash="x")

        def race() -> None:
            with Session(bind=engine) as second:
                reached.set()
                outcomes.append(
                    UserRepository(second).create_first_admin(email=SECOND, name="Segundo", password_hash="x")
                )

        worker = threading.Thread(target=race, daemon=True)
        worker.start()
        assert reached.wait(timeout=5), "the second call never started"

        worker.join(timeout=BLOCKED_PATIENCE_SECONDS)
        assert worker.is_alive(), (
            "the second call finished while the first was uncommitted: the predicate is not atomic, "
            "which is two administrators on a fresh install (ADR 0011)"
        )

        first.commit()
        worker.join(timeout=10)
        assert not worker.is_alive()

        assert outcomes == [None], "the second call created an account on a table that already had one"
        assert _count(engine) == 1
    finally:
        # Release the lock before waiting on the thread, or a failed assertion would leave the worker
        # inserting behind the cleanup.
        first.rollback()
        first.close()
        if worker is not None:
            worker.join(timeout=10)
        _remove_what_this_file_wrote(engine)

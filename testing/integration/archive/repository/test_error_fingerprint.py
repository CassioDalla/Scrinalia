"""The root cause is PostgreSQL's, and it has to group the same failure without merging other ones.

The fingerprint is a generated column over the error text, so "does it group correctly?" is a
question about the database, not about a Python function. These tests pin the three properties the
failures screen depends on: a varying id is the *same* cause, a different exception class over the
same sentence is *not* the same cause, and a run that never failed has no cause at all.
"""

from sqlalchemy import select, text

from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from memoria_curitibana.domains.archive.models.operations import ApiError, WorkerRun
from memoria_curitibana.domains.archive.repository.worker_run_repo import WorkerRunRepository


def fingerprint(db, message: str | None) -> str | None:
    """The function under test, called directly so the column is not in the way of the question."""
    return db.scalar(text("SELECT public.archive_error_fingerprint(:message)"), {"message": message})


def test_a_varying_id_is_the_same_cause(db_session) -> None:
    first = fingerprint(db_session, "FileNotFoundError: [Errno 2] No such file or directory: '/acervo/thumb_4821.jpg'")
    second = fingerprint(db_session, "FileNotFoundError: [Errno 2] No such file or directory: '/acervo/thumb_9130.jpg'")

    assert first == second
    assert first == "filenotfounderror: [errno <n>] no such file or directory: '<path>'"


def test_the_numbers_of_a_message_do_not_split_one_cause(db_session) -> None:
    first = fingerprint(db_session, "ConnectionError: HTTPConnectionPool(host='localhost', port=11434)")
    second = fingerprint(db_session, "ConnectionError: HTTPConnectionPool(host='localhost', port=11435)")

    assert first == second
    assert first == "connectionerror: httpconnectionpool(host='localhost', port=<n>)"


def test_a_different_class_over_the_same_sentence_is_a_different_cause(db_session) -> None:
    """Without the class in the text, ``TimeoutError: boom`` and ``ValueError: boom`` would merge."""
    assert fingerprint(db_session, "TimeoutError: boom") != fingerprint(db_session, "ValueError: boom")


def test_a_null_error_has_no_cause(db_session) -> None:
    assert fingerprint(db_session, None) is None


def test_the_ledger_stamps_the_class_the_fingerprint_is_computed_from(db_session) -> None:
    """The repository composes ``Classe: mensagem``; the generated column reads exactly that text."""
    repo = WorkerRunRepository(db_session)
    run = repo.create_queued(
        "ner",
        trigger=WorkerRunTrigger.CLI,
        requested_by=None,
        engine_name="spacy_ner",
        preset="cpu_local",
        config={},
    )

    repo.finish(run.run_id, status=WorkerRunStatus.FAILED, error="'nome'", error_kind="KeyError")
    db_session.expire_all()

    row = db_session.get(WorkerRun, run.run_id)
    assert row is not None
    assert row.error == "KeyError: 'nome'"
    assert row.error_fingerprint == fingerprint(db_session, "KeyError: 'nome'")


def test_an_exception_without_a_message_still_records_its_class(db_session) -> None:
    """A bare ``raise RuntimeError()`` has a class and no text; recording nothing would be a lie."""
    repo = WorkerRunRepository(db_session)
    run = repo.create_queued(
        "ner",
        trigger=WorkerRunTrigger.CLI,
        requested_by=None,
        engine_name=None,
        preset=None,
        config={},
    )

    repo.finish(run.run_id, status=WorkerRunStatus.FAILED, error="", error_kind="RuntimeError")
    db_session.expire_all()

    row = db_session.get(WorkerRun, run.run_id)
    assert row is not None
    assert row.error == "RuntimeError"
    assert row.error_fingerprint == "runtimeerror"


def test_the_api_error_ledger_shares_the_definition(db_session) -> None:
    """One function, two tables: a cause that breaks a worker and a request is one root cause."""
    db_session.add(
        ApiError(
            request_id="trace-42",
            method="GET",
            path="/api/v1/documents/4821",
            status_code=500,
            message="KeyError: 'nome'",
        )
    )
    db_session.flush()
    db_session.expire_all()

    row = db_session.scalars(select(ApiError)).one()
    assert row.error_fingerprint == fingerprint(db_session, "KeyError: 'nome'")

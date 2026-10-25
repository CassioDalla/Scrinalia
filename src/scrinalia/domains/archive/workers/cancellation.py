"""The one place a worker asks whether the operator stopped it (ADR 0014 decision 9, #72).

A cancellation is a **request**, never a thread kill: ``ThreadPoolExecutor`` cannot interrupt a
running thread, and a torch forward pass cannot be interrupted from Python. The granularity is
therefore one batch (``db_batch_size``, 64 by default): the worker finishes the batch it started,
commits it, and stops before fetching the next one. That is what keeps the archive consistent —
stopping mid-batch would roll back work the operator asked to keep.

``RunControl`` carries the two sources of the request and joins them in one ``checkpoint()``:

* ``request_stop()`` is the in-process half, set by the CLI's signal handler. It is the only way to
  stop a run whose row the process cannot read (a database outage) and the only half that works
  without a ledger.
* ``cancel_requested_at`` in the ledger is the panel's half, written by ``POST /system/runs/{id}/cancel``
  and read once per batch through ``WorkerRunLedger.cancel_requested``.

``WorkerRunCancelled`` inherits ``BaseException`` on purpose. Every worker wraps its batch in
``except Exception`` to turn a broken batch into "log it and leave the loop"; a cancellation is not
a broken batch, and letting one of those handlers swallow it would finish the run ``SUCCESS`` after
the operator stopped it. ``asyncio.CancelledError`` inherits ``BaseException`` for the same reason.

The check is one function consulted once per batch by every worker that loops. A test walks the
catalogue and fails when a looping worker does not call ``checkpoint(run_control)`` inside its
``while`` — the same gate shape the repository uses for the queue predicates (principle V).
"""

from __future__ import annotations

import threading

from scrinalia.domains.archive.workers.ledger import WorkerRunLedger


class WorkerRunCancelled(BaseException):
    """The operator asked this run to stop; raised at a batch boundary, never mid-batch."""


class RunControl:
    """
    The cancellation state of one execution, shared by the runner and the worker it calls.

    One instance per run, created by ``run_worker`` (or by the CLI before it knows the run id, then
    bound to it). ``checkpoint`` is called by the worker at the top of every batch; when it raises,
    the worker's ``execute`` unwinds and ``run_worker`` closes the ledger row ``CANCELLED``.
    """

    def __init__(self, *, ledger: WorkerRunLedger | None = None, run_id: int | None = None) -> None:
        self._ledger = ledger
        self._run_id = run_id
        self._stop = threading.Event()

    def bind(self, run_id: int, ledger: WorkerRunLedger) -> None:
        """
        Attaches the row this control belongs to.

        The CLI creates the control before ``run_worker`` opens the row, so the signal can reach it
        first; the binding happens after ``ledger.start`` returns the id. Rebinding to a different
        run is a programming error: one control belongs to one execution.
        """
        if self._run_id is not None and self._run_id != run_id:
            raise RuntimeError(f"this RunControl already belongs to run {self._run_id}, not {run_id}")
        self._ledger = ledger
        self._run_id = run_id

    def request_stop(self) -> None:
        """Sets the in-process half of the request; the CLI's signal handler calls it."""
        self._stop.set()

    @property
    def stop_requested(self) -> bool:
        """Whether the in-process half was set. The database half is checked at ``checkpoint``."""
        return self._stop.is_set()

    def checkpoint(self) -> None:
        """
        Raises ``WorkerRunCancelled`` when a stop was requested; the one call per batch.

        The local flag is consulted first because it is free and it is the signal path. The ledger
        read is a single indexed row and happens once per batch, next to the batch's own query.
        """
        if self._stop.is_set():
            raise WorkerRunCancelled("a stop was requested by the process")
        if self._run_id is None or self._ledger is None:
            return
        if self._ledger.cancel_requested(self._run_id):
            raise WorkerRunCancelled(f"a cancellation was requested for run {self._run_id}")


def checkpoint(run_control: RunControl | None) -> None:
    """
    The worker-facing form: consult the control, or do nothing for a programmatic run.

    A worker called without a ledger (a test, ``execute(db)`` by hand) has no run to cancel, and
    ``None`` is the whole of that case. Keeping it here rather than as an ``if`` in every loop is
    what makes the workers nine identical one-line calls instead of nine copies of the rule.
    """
    if run_control is not None:
        run_control.checkpoint()

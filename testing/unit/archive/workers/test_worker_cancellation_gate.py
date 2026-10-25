"""A cancellation is consulted once per batch by every worker that loops (#72).

The gate is deliberately structural. A behavioural test would have to build the engine — spaCy for
NER, torch for the embedding — and would spend minutes proving one line; a source test walks the
catalogue, finds the ``while`` loops of each ``execute`` and fails when one of them does not call
``checkpoint(run_control)``. It is the same shape as the queue-predicate gates: the fact is derived
from the code, not from a second declaration that could drift from it.

The detector's limit is stated instead of hidden: a worker that delegates its loop to a helper is not
seen. When that happens, the helper is the place to check, and this file is where the new worker's
spec is added.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import pytest

import scrinalia
from scrinalia.domains.archive.workers.cancellation import RunControl, WorkerRunCancelled, checkpoint
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger

#: The workers that sweep in batches today. It is a *detector* check, not the gate itself: if the
#: source walk stopped seeing one of them (a rename, a moved loop), the gate would pass vacuously.
KNOWN_LOOPERS = frozenset({"cleaning", "embedding", "macro-category", "ner", "quality-validator", "typology"})


def _module_path(module: str) -> Path:
    """The source file of a catalogue module, without importing it (the catalogue is lazy on purpose)."""
    return Path(scrinalia.__file__).parent / Path(*module.split(".")[1:]).with_suffix(".py")


def _execute(spec) -> ast.FunctionDef:
    source = _module_path(spec.module).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=spec.module)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "execute":
            return node
    raise AssertionError(f"{spec.module} declares no module-level execute()")


def _loops(execute: ast.FunctionDef) -> list[ast.While]:
    return [node for node in ast.walk(execute) if isinstance(node, ast.While)]


def _declares_control(execute: ast.FunctionDef) -> bool:
    args = execute.args
    declared = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    return "run_control" in {arg.arg for arg in declared}


def _consults_checkpoint(loop: ast.While) -> bool:
    """
    Whether the loop body calls ``checkpoint(run_control)``.

    The call is recognised by name and by argument: a worker that consults some other control is
    not consulting this run's. The position inside the loop is not pinned — a check at the end of
    the body is still one per batch — but every loop of the function must have one.
    """

    def is_the_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "checkpoint"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "run_control"
        )

    return any(is_the_call(node) for node in ast.walk(loop))


def test_every_looping_worker_consults_the_cancellation_at_the_batch_boundary() -> None:
    discovered: dict[str, tuple[ast.FunctionDef, list[ast.While]]] = {}
    for name, spec in WORKER_CATALOGUE.items():
        execute = _execute(spec)
        loops = _loops(execute)
        if loops:
            discovered[name] = (execute, loops)

    missing_workers = sorted(KNOWN_LOOPERS - set(discovered))
    assert not missing_workers, (
        f"the source walk no longer sees the loops of {missing_workers}: the gate below would pass "
        "without checking them. Fix the detector before trusting a green run."
    )

    offenders = sorted(
        name
        for name, (execute, loops) in discovered.items()
        if not _declares_control(execute) or not all(_consults_checkpoint(loop) for loop in loops)
    )
    assert not offenders, (
        f"these workers loop without consulting the cancellation in every batch: {offenders}. "
        "A cancellation is a request honoured at the batch boundary (ADR 0014 decision 9); add "
        "`checkpoint(run_control)` to the top of the loop and `run_control` to the signature."
    )


def test_the_checkpoint_is_a_no_op_for_a_run_without_a_control() -> None:
    """A programmatic ``execute(db)`` has no row to cancel; ``None`` is the whole of that case."""
    checkpoint(None)


def test_a_signal_stop_is_honoured_at_the_next_checkpoint() -> None:
    control = RunControl()
    checkpoint(control)  # nothing requested yet

    control.request_stop()
    assert control.stop_requested is True

    with pytest.raises(WorkerRunCancelled):
        checkpoint(control)


class _RequestedLedger:
    """The one method ``RunControl`` uses, so the test needs no database."""

    def __init__(self, requested: bool) -> None:
        self.requested = requested
        self.seen: list[int] = []

    def cancel_requested(self, run_id: int) -> bool:
        self.seen.append(run_id)
        return self.requested


def test_the_panel_request_is_read_from_the_ledger_at_the_checkpoint() -> None:
    ledger = _RequestedLedger(requested=True)
    control = RunControl(ledger=cast(WorkerRunLedger, ledger), run_id=7)

    with pytest.raises(WorkerRunCancelled):
        control.checkpoint()

    assert ledger.seen == [7]


def test_the_request_is_not_read_before_the_control_is_bound() -> None:
    """The CLI creates the control before the row exists; an unbound checkpoint only sees the signal."""
    ledger = _RequestedLedger(requested=True)
    control = RunControl(ledger=cast(WorkerRunLedger, ledger))

    control.checkpoint()

    assert ledger.seen == []


def test_a_control_belongs_to_one_execution() -> None:
    ledger = cast(WorkerRunLedger, _RequestedLedger(requested=False))
    control = RunControl(ledger=ledger, run_id=1)

    with pytest.raises(RuntimeError, match="already belongs to run 1"):
        control.bind(2, ledger)

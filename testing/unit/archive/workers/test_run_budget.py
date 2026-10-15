"""The cap of one bounded run: what ``--limit`` counts, and that a run cannot overshoot it."""

import pytest

from scrinalia.domains.archive.workers.run_budget import RunBudget


def test_an_unbounded_run_never_narrows_the_batch() -> None:
    budget = RunBudget()

    assert budget.batch_size(64) == 64
    budget.spend(1_000)
    assert budget.exhausted is False
    assert budget.batch_size(64) == 64


def test_the_last_batch_is_narrowed_to_what_is_left() -> None:
    budget = RunBudget(limit=3)

    assert budget.batch_size(2) == 2
    budget.spend(2)
    assert budget.exhausted is False
    # The third unit is the whole of what is left: a batch of two would overshoot the cap.
    assert budget.batch_size(2) == 1
    budget.spend(1)
    assert budget.exhausted is True
    assert budget.batch_size(2) == 0


@pytest.mark.parametrize("touched", [3, 4])
def test_the_cap_counts_attempts_not_successes(touched: int) -> None:
    """A queue of failures has to let a bounded run end, so an attempt spends the budget."""
    budget = RunBudget(limit=3)
    budget.spend(touched)

    assert budget.exhausted is True
    assert budget.batch_size(64) == 0

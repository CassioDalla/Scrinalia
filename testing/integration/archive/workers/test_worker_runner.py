"""The command line gets the panel's refusals: both resolve their configuration in one place.

``resolve_configuration`` is the single path the CLI, the trigger route and the settings screen all
go through, so the engine check lives there. It used to live only in the two API services: on the
command line ``--engine`` reached a worker whose engine comes from the active ``LLM_CHECK`` rule,
won over the rule and was forwarded to the worker as an engine kwarg.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError
from scrinalia.domains.archive.workers import runner

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@contextmanager
def _factory(db: Session):
    yield db


def test_the_cli_refuses_an_engine_a_worker_does_not_take(db_session: Session) -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="LLM_CHECK"):
        runner.run_worker(
            "quality-validator",
            engine_name="bertopic",
            db_factory=lambda: _factory(db_session),
        )


def test_the_cli_refuses_a_worker_that_carries_no_engine(db_session: Session) -> None:
    """The other half of the same refusal: a worker with no model cannot be given one."""
    with pytest.raises(InvalidWorkerSettingsError, match="não carrega modelo"):
        runner.run_worker(
            "transfer",
            engine_name="bertopic",
            db_factory=lambda: _factory(db_session),
        )

"""
The judge engine's failure path (issue #122).

``EntityTagDecisionSchema`` has no "I could not answer" state, so a failed call used to come back as a
verdict — ``winner="TAG"`` with confidence ``0.0`` — and the worker wrote it into the review queue,
where the curation inbox showed a decision the model never took. The engine now **raises**
``EngineExecutionError``: the type is what tells a failure from an opinion, and both the worker and
the bench read it instead of a prefix inside a free-text ``reason``.
"""

from __future__ import annotations

import pytest
import requests

from scrinalia.domains.archive.engines.LLMs.ollama_tag_entity_conflict import OllamaJudgeEngine
from scrinalia.domains.archive.exceptions import EngineExecutionError


def test_a_transport_failure_raises_instead_of_returning_a_verdict(mocker) -> None:
    mocker.patch.object(requests, "post", side_effect=requests.ConnectionError("connection refused"))

    with pytest.raises(EngineExecutionError, match="não respondeu"):
        OllamaJudgeEngine().decide_conflict(tag_name="parques", entity_name="parques", entity_type="LOC")


def test_a_server_error_raises_too(mocker) -> None:
    """Measured on this machine: a 500 reaches the engine as an ``HTTPError``, not as a body."""
    response = mocker.Mock()
    response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mocker.patch.object(requests, "post", return_value=response)

    with pytest.raises(EngineExecutionError):
        OllamaJudgeEngine().decide_conflict(tag_name="parques", entity_name="parques", entity_type="LOC")


def test_a_body_that_is_not_a_verdict_raises(mocker) -> None:
    """
    A 200 whose body is not the JSON schema is a failure too.

    The old ``except`` covered this as well, and it is the quiet half of the defect: the call
    succeeded and the answer was still not a decision, so a return of ``winner="TAG"`` here would be
    just as fabricated as on a connection error.
    """
    response = mocker.Mock()
    response.json.return_value = {"response": "não é json"}
    mocker.patch.object(requests, "post", return_value=response)

    with pytest.raises(EngineExecutionError):
        OllamaJudgeEngine().decide_conflict(tag_name="parques", entity_name="parques", entity_type="LOC")


def test_a_valid_answer_is_still_a_verdict(mocker) -> None:
    """The raise must not swallow the happy path: a parsed body is returned, not wrapped in an error."""
    response = mocker.Mock()
    response.json.return_value = {"response": '{"winner": "ENTITY", "confidence": 0.9, "reason": "Regra 1"}'}
    mocker.patch.object(requests, "post", return_value=response)

    decision = OllamaJudgeEngine().decide_conflict(tag_name="parques", entity_name="parques", entity_type="LOC")

    assert decision.winner == "ENTITY"
    assert decision.confidence == 0.9

"""
The judge engine's failure path (issue #114).

``EntityTagDecisionSchema`` has no "I could not answer" state, so a transport failure comes back as a
verdict — ``winner="TAG"`` with confidence ``0.0``. The bench that scores the judge has to be able to
tell the two apart, and the only thing that distinguishes them is the reason's prefix
(``testing/unit/evaluation/test_conflict_judge_quality.py`` pins the bench's side of that pair), so
this file pins the engine's: a failure always carries it.
"""

from __future__ import annotations

import requests

from scrinalia.domains.archive.engines.LLMs.ollama_tag_entity_conflict import (
    FAILURE_REASON_PREFIX,
    OllamaJudgeEngine,
)


def test_a_failed_call_returns_the_prefix_that_marks_it_a_failure(mocker) -> None:
    mocker.patch.object(requests, "post", side_effect=requests.ConnectionError("connection refused"))

    decision = OllamaJudgeEngine().decide_conflict(tag_name="parques", entity_name="parques", entity_type="LOC")

    assert decision.winner == "TAG"
    assert decision.confidence == 0.0
    assert decision.reason.startswith(FAILURE_REASON_PREFIX)


def test_a_server_error_is_a_failure_too(mocker) -> None:
    """Measured on this machine: ``granite4.1:3b`` answers 500 for every prompt, and Ollama returns it."""
    response = mocker.Mock()
    response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mocker.patch.object(requests, "post", return_value=response)

    decision = OllamaJudgeEngine().decide_conflict(tag_name="parques", entity_name="parques", entity_type="LOC")

    assert decision.reason.startswith(FAILURE_REASON_PREFIX)


def test_the_prefix_carries_text() -> None:
    """
    A prefix of ``""`` would mark every verdict a failure, and the bench would score nothing at all.

    An empty prefix is not a theoretical slip: it is what ``"".join`` and a deleted constant both look
    like, and it fails in the direction that produces a zero.
    """
    assert FAILURE_REASON_PREFIX
    assert not FAILURE_REASON_PREFIX.startswith(" ")

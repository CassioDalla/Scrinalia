"""Behaviour of the tag x entity conflict judge.

The engine is shielded by ``mock_registry``; what is under test here is the worker's
own logic: when it auto-resolves, when it defers to a human, and how it protects
itself against reprocessing the same pair.
"""

from unittest.mock import MagicMock

from sqlalchemy import select

from memoria_curitibana.domains.archive.engines.LLMs import registry as llm_registry
from memoria_curitibana.domains.archive.models import ArchiveReviewStatus
from memoria_curitibana.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from memoria_curitibana.domains.archive.repository.entity_repo import EntityRepository
from memoria_curitibana.domains.archive.schemas.ai_schemas import EntityTagDecisionSchema

# The repository is what talks to Postgres; the conflicts it returns are faked so the
# test exercises the worker's decisions, not pg_trgm.
from memoria_curitibana.domains.archive.schemas.entity_schema import CrossDomainConflict
from memoria_curitibana.domains.archive.workers import worker_resolve_tag_entity_conflict as worker


def _conflict(tag_id: int = 1, entity_id: int = 10) -> CrossDomainConflict:
    return CrossDomainConflict(
        tag_id=tag_id,
        tag_name="parques",
        entity_id=entity_id,
        entity_name="parques",
        entity_type="LOC",
        similarity=0.95,
    )


def _decision(winner: str = "ENTITY", confidence: float = 0.95, reason: str = "Regra 1: nome de lugar") -> MagicMock:
    return EntityTagDecisionSchema(winner=winner, confidence=confidence, reason=reason)


def _queue_entries(db_session) -> list[ArchiveAIReviewQueue]:
    return list(db_session.scalars(select(ArchiveAIReviewQueue)).all())


# ==========================================
# 1. AUTO-RESOLUTION (HIGH CONFIDENCE)
# ==========================================


def test_high_confidence_resolves_and_records_ai_approved(db_session, mocker, mock_registry):
    """Above the threshold the conflict is settled without a human."""
    engine = mock_registry(llm_registry)
    engine.return_value.decide_conflict.return_value = _decision(confidence=0.95)
    mocker.patch.object(EntityRepository, "get_cross_domain_conflicts", return_value=[_conflict()])
    resolve = mocker.patch.object(EntityRepository, "resolve_cross_domain_conflict")

    worker.execute(db=db_session, auto_resolve_threshold=0.85)

    resolve.assert_called_once_with(winner="ENTITY", tag_id=1, entity_id=10)
    entries = _queue_entries(db_session)
    assert len(entries) == 1
    assert entries[0].status == ArchiveReviewStatus.AI_APPROVED
    assert entries[0].llm_decision == "ENTITY"


def test_low_confidence_defers_to_human_review(db_session, mocker, mock_registry):
    """Below the threshold the repository must not be touched: a human decides."""
    engine = mock_registry(llm_registry)
    engine.return_value.decide_conflict.return_value = _decision(confidence=0.40, reason="Regra 3: ambíguo")
    mocker.patch.object(EntityRepository, "get_cross_domain_conflicts", return_value=[_conflict()])
    resolve = mocker.patch.object(EntityRepository, "resolve_cross_domain_conflict")

    worker.execute(db=db_session, auto_resolve_threshold=0.85)

    resolve.assert_not_called()
    entries = _queue_entries(db_session)
    assert len(entries) == 1
    assert entries[0].status == ArchiveReviewStatus.NEEDS_REVIEW
    assert entries[0].llm_reason == "Regra 3: ambíguo"


def test_confidence_exactly_at_the_threshold_resolves(db_session, mocker, mock_registry):
    """The boundary is inclusive; pin it so a refactor cannot flip it silently."""
    engine = mock_registry(llm_registry)
    engine.return_value.decide_conflict.return_value = _decision(confidence=0.85)
    mocker.patch.object(EntityRepository, "get_cross_domain_conflicts", return_value=[_conflict()])
    resolve = mocker.patch.object(EntityRepository, "resolve_cross_domain_conflict")

    worker.execute(db=db_session, auto_resolve_threshold=0.85)

    resolve.assert_called_once()
    assert _queue_entries(db_session)[0].status == ArchiveReviewStatus.AI_APPROVED


# ==========================================
# 2. FAILURE HANDLING
# ==========================================


def test_database_failure_during_resolution_falls_back_to_human(db_session, mocker, mock_registry):
    """A failing write must not lose the evaluation: it is queued for review instead."""
    engine = mock_registry(llm_registry)
    engine.return_value.decide_conflict.return_value = _decision(confidence=0.99)
    mocker.patch.object(EntityRepository, "get_cross_domain_conflicts", return_value=[_conflict()])
    mocker.patch.object(
        EntityRepository, "resolve_cross_domain_conflict", side_effect=RuntimeError("constraint violation")
    )

    worker.execute(db=db_session, auto_resolve_threshold=0.85)

    entries = _queue_entries(db_session)
    assert len(entries) == 1
    assert entries[0].status == ArchiveReviewStatus.NEEDS_REVIEW
    assert "FALHA NO BANCO" in entries[0].llm_reason


def test_engine_failure_aborts_before_scanning(db_session, mocker, mock_registry):
    """If the judge cannot be built there is nothing to do, and no silent half-run."""
    engine = mock_registry(llm_registry)
    engine.side_effect = RuntimeError("ollama unreachable")
    scan = mocker.patch.object(EntityRepository, "get_cross_domain_conflicts")

    worker.execute(db=db_session)

    scan.assert_not_called()
    assert _queue_entries(db_session) == []


# ==========================================
# 3. IDEMPOTENCY
# ==========================================


def test_empty_scan_stops_early(db_session, mocker, mock_registry):
    """No conflicts means no queue entries and no engine calls."""
    engine = mock_registry(llm_registry)
    mocker.patch.object(EntityRepository, "get_cross_domain_conflicts", return_value=[])

    worker.execute(db=db_session)

    engine.return_value.decide_conflict.assert_not_called()
    assert _queue_entries(db_session) == []


def test_already_queued_pair_is_not_evaluated_again(db_session, mocker, mock_registry):
    """Regression guard: re-running the worker must not pay the LLM twice for one pair."""
    engine = mock_registry(llm_registry)
    db_session.add(
        ArchiveAIReviewQueue(
            anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
            status=ArchiveReviewStatus.NEEDS_REVIEW,
            context_payload={"tag_id": 1, "entity_id": 10},
            llm_decision="ENTITY",
            llm_confidence=0.5,
            llm_reason="anterior",
        )
    )
    db_session.commit()

    engine.return_value.decide_conflict.return_value = _decision(confidence=0.99)
    mocker.patch.object(EntityRepository, "get_cross_domain_conflicts", return_value=[_conflict()])
    resolve = mocker.patch.object(EntityRepository, "resolve_cross_domain_conflict")

    worker.execute(db=db_session)

    engine.return_value.decide_conflict.assert_not_called()
    resolve.assert_not_called()
    assert len(_queue_entries(db_session)) == 1


def test_each_conflict_is_evaluated_once(db_session, mocker, mock_registry):
    """Multiple distinct pairs are all processed."""
    engine = mock_registry(llm_registry)
    engine.return_value.decide_conflict.return_value = _decision(confidence=0.10)
    mocker.patch.object(
        EntityRepository,
        "get_cross_domain_conflicts",
        return_value=[_conflict(tag_id=1, entity_id=10), _conflict(tag_id=2, entity_id=20)],
    )

    worker.execute(db=db_session, auto_resolve_threshold=0.85)

    assert engine.return_value.decide_conflict.call_count == 2
    assert len(_queue_entries(db_session)) == 2

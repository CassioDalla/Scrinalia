"""Integration tests of the structural anomaly validator (real PostgreSQL)."""

from sqlalchemy import select

from scrinalia.domains.archive.models import (
    AnomalyReason,
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTypology,
)
from scrinalia.domains.archive.schemas.ai_schemas import TitleQualityDecision
from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO
from scrinalia.domains.archive.workers.worker_quality_validator import execute

LLM_REGISTRY = "scrinalia.domains.archive.engines.title_quality.registry.get_engine"


def _complete_document(db_session, **overrides):
    """A document with everything the validator expects, so only the tested gap remains."""
    typology = ArchiveTypology(typology_id=991, name="Dossiê")
    tag = ArchiveTag(tag_id=991, name="urbanismo")
    entity = ArchiveEntity(entity_id=991, name="Curitiba", entity_type="LOC")
    db_session.add_all([typology, tag, entity])
    db_session.flush()

    doc = ArchiveDocument(
        description_id=overrides.pop("description_id", "valid-1"),
        original_title=overrides.pop("original_title", "Rua Izaac Ferreira da Cruz"),
        document_date=overrides.pop("document_date", None) or __import__("datetime").date(1954, 3, 15),
        typology_id=991,
        staging_content_hash="h" * 12,
        **(overrides.pop("extra", {})),
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag.tag_id),
            ArchiveDocumentEntity(description_id=doc.description_id, entity_id=entity.entity_id),
        ]
    )
    db_session.flush()
    return doc


def test_worker_marks_every_gap_and_sends_the_document_to_review(db_session, generate_archive_doc) -> None:
    doc = generate_archive_doc(description_id="gap-1", original_title="SEM TÍTULO", scope_content="   ")
    description_id = doc.description_id

    execute(db=db_session)

    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, description_id)
    assert stored.is_anomaly is True
    assert set(stored.anomaly_reasons) >= {
        AnomalyReason.MISSING_DATE,
        AnomalyReason.EMPTY_TITLE,
        AnomalyReason.NO_TAGS,
        AnomalyReason.NO_TYPOLOGY,
        AnomalyReason.NO_ENTITIES,
    }
    assert stored.review_status == ArchiveReviewStatus.NEEDS_REVIEW
    assert "worker_quality_validator_v1" in stored.execution_log


def test_worker_clears_the_reasons_of_a_complete_document(db_session) -> None:
    doc = _complete_document(db_session, description_id="valid-2")
    description_id = doc.description_id

    execute(db=db_session)

    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, description_id)
    assert stored.is_anomaly is False
    assert stored.anomaly_reasons is None
    assert stored.review_status == ArchiveReviewStatus.PENDING_AI


def test_worker_never_touches_a_human_approved_document(db_session, generate_archive_doc) -> None:
    doc = generate_archive_doc(
        description_id="approved-1",
        original_title="SEM TÍTULO",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )
    description_id = doc.description_id

    execute(db=db_session)

    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, description_id)
    assert stored.is_anomaly is False
    assert stored.anomaly_reasons is None
    assert stored.review_status == ArchiveReviewStatus.HUMAN_APPROVED


def test_worker_does_not_reprocess_a_stamped_document(db_session, generate_archive_doc) -> None:
    doc = generate_archive_doc(description_id="stamped-1", execution_log={"worker_quality_validator_v1": "DONE"})
    description_id = doc.description_id

    execute(db=db_session)

    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, description_id)
    assert stored.is_anomaly is False


def test_worker_applies_an_archivist_validate_rule(db_session, generate_archive_doc) -> None:
    from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository

    repository = CleaningRepository(db_session)
    repository.create_rule(
        CleaningRuleCreateDTO(
            rule_name="Título com código",
            target_column="original_title",
            regex_pattern=r"\b\d{4}-\d{2}\b",
            replacement_string="",
            rule_kind="VALIDATE",
            anomaly_reason="Código de controle no título",
        )
    )
    db_session.flush()
    doc = generate_archive_doc(description_id="rule-1", original_title="Obras 2023-07 na Rua X")
    description_id = doc.description_id

    execute(db=db_session)

    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, description_id)
    assert f"{AnomalyReason.RULE_MATCH}:Código de controle no título" in stored.anomaly_reasons


def test_worker_does_not_build_a_model_without_an_llm_rule(db_session, generate_archive_doc, mocker) -> None:
    """The default is deterministic validation: no rule means no model is instantiated."""
    mocked_get_engine = mocker.patch(LLM_REGISTRY)
    generate_archive_doc(description_id="no-llm-1")

    execute(db=db_session)

    mocked_get_engine.assert_not_called()


def test_worker_uses_the_llm_when_a_rule_is_active(db_session, generate_archive_doc, mocker) -> None:
    from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository

    mocked_get_engine = mocker.patch(LLM_REGISTRY)
    mocked_get_engine.return_value.check_title.return_value = TitleQualityDecision(
        is_suspect=True, confidence=0.95, reason="título truncado"
    )
    CleaningRepository(db_session).create_rule(
        CleaningRuleCreateDTO(
            rule_name="Revisão de título por LLM",
            target_column="original_title",
            regex_pattern=".",
            replacement_string="",
            rule_kind="LLM_CHECK",
            engine_name="ollama_title_check",
            preset="granite_local",
        )
    )
    db_session.flush()
    doc = generate_archive_doc(description_id="llm-1", original_title="Rua Izaac Ferreir")
    description_id = doc.description_id

    execute(db=db_session)

    mocked_get_engine.assert_called_once()
    assert mocked_get_engine.call_args.args[0] == "ollama_title_check"
    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, description_id)
    assert f"{AnomalyReason.LLM_SUSPECT}:título truncado" in stored.anomaly_reasons


def test_the_cleaning_worker_ignores_validation_rules(db_session, generate_archive_doc) -> None:
    """Safety: a VALIDATE rule must never substitute text the way a REWRITE rule does."""
    from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository
    from scrinalia.domains.archive.workers.worker_cleaning_regex import execute as run_cleaning

    CleaningRepository(db_session).create_rule(
        CleaningRuleCreateDTO(
            rule_name="Não pode reescrever",
            target_column="original_title",
            regex_pattern="Rua",
            replacement_string="APAGADO",
            rule_kind="VALIDATE",
        )
    )
    db_session.flush()
    doc = generate_archive_doc(description_id="safe-1", original_title="Rua Izaac")
    description_id = doc.description_id

    run_cleaning(db=db_session)

    db_session.expire_all()
    assert db_session.get(ArchiveDocument, description_id).original_title == "Rua Izaac"


def test_validator_stamp_is_searchable_in_the_execution_log(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="log-1")

    execute(db=db_session)

    db_session.expire_all()
    logs = db_session.scalars(
        select(ArchiveDocument.execution_log).where(ArchiveDocument.description_id == "log-1")
    ).one()
    assert logs["worker_quality_validator_v1"] == "DONE"

"""The panel's read model and the settings writes, against the database."""

import pytest

from scrinalia.core.author import Author
from scrinalia.core.runner_config import TypologyRunnerConfig
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError, WorkerNotFoundError
from scrinalia.domains.archive.models.operations import WorkerSetting
from scrinalia.domains.archive.repository import TypologyRepository
from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository
from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO
from scrinalia.domains.archive.schemas.system_schema import WorkerSettingsRequest
from scrinalia.domains.archive.services.worker_operations_service import WorkerOperationsService
from scrinalia.domains.archive.worker_stamp import NER, TYPOLOGY
from scrinalia.domains.archive.workers import runner, worker_typology


@pytest.fixture
def service(db_session) -> WorkerOperationsService:
    return WorkerOperationsService(db_session)


def test_the_panel_lists_the_whole_pipeline_in_order(service) -> None:
    response = service.list_workers()

    assert [worker.name for worker in response.workers] == runner.PIPELINE_ORDER
    assert [worker.order for worker in response.workers] == list(range(len(runner.PIPELINE_ORDER)))


def test_a_signature_worker_shows_the_code_default_and_the_resolved_model(service) -> None:
    ner = next(worker for worker in service.list_workers().workers if worker.name == "ner")

    assert ner.settings.engine_name == "spacy_ner"
    assert ner.settings.preset == "gpu"
    assert ner.settings.config["model"] == "pt_core_news_lg"
    assert ner.settings.overridden is False
    assert [engine.name for engine in ner.settings.available_engines] == ["spacy_ner"]


def test_the_unmeasurable_worker_says_why_instead_of_guessing(service) -> None:
    judge = next(worker for worker in service.list_workers().workers if worker.name == "conflict-judge")

    assert judge.pending is None
    assert judge.pending_reason
    assert "53" in judge.pending_reason or "trigram" in judge.pending_reason
    assert judge.processed == 0


def test_the_quality_validator_takes_its_engine_from_the_active_rule(db_session, service) -> None:
    deterministic = next(worker for worker in service.list_workers().workers if worker.name == "quality-validator")
    assert deterministic.settings.engine_name is None
    assert deterministic.settings.note and "LLM_CHECK" in deterministic.settings.note

    CleaningRepository(db_session).create_rule(
        CleaningRuleCreateDTO(
            rule_name="Revisão de título",
            target_column="original_title",
            regex_pattern=".",
            replacement_string="",
            rule_kind="LLM_CHECK",
            engine_name="ollama_title_check",
            preset="gemma_4b_local",
        )
    )
    db_session.flush()

    with_rule = next(worker for worker in service.list_workers().workers if worker.name == "quality-validator")
    assert with_rule.settings.engine_name == "ollama_title_check"
    assert with_rule.settings.preset == "gemma_4b_local"
    assert with_rule.settings.config["model"] == "gemma4:e4b"


def test_a_setting_round_trips_and_leaves_a_revision(db_session, service) -> None:
    updated = service.update_settings(
        "ner",
        WorkerSettingsRequest(engine_name="spacy_ner", preset="lemmatizer", db_batch_size=16),
        changed_by=Author(name="teste"),
    )
    assert updated.overridden is True
    assert updated.preset == "lemmatizer"
    assert updated.db_batch_size == 16
    assert updated.updated_by == "teste"

    revisions = service.list_revisions("ner", limit=10, offset=0)
    assert revisions.total == 1
    assert revisions.items[0].before is None
    assert revisions.items[0].after is not None
    assert revisions.items[0].after["preset"] == "lemmatizer"

    cleared = service.clear_settings("ner", changed_by=Author(name="teste"))
    assert cleared.overridden is False
    assert cleared.preset == "gpu"
    assert service.list_revisions("ner", limit=10, offset=0).total == 2


def test_the_effective_configuration_follows_the_persisted_override(service) -> None:
    service.update_settings("embedding", WorkerSettingsRequest(db_batch_size=8, options={"force": True}))

    embedding = next(worker for worker in service.list_workers().workers if worker.name == "embedding")
    assert embedding.settings.db_batch_size == 8
    assert embedding.settings.options == {"force": True}
    # ``force`` widens the queue: every non-rejected document is pending again.
    assert embedding.pending is not None


def test_an_unknown_engine_or_option_is_rejected(service) -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="não existe para o eixo"):
        service.update_settings("ner", WorkerSettingsRequest(engine_name="motor_inexistente"))

    # ``force`` is a declared option of the thumbnail worker now (it is the way back from a mark a
    # transient outage left behind); an option the worker does not declare is still refused.
    with pytest.raises(InvalidWorkerSettingsError, match="não aceita a opção"):
        service.update_settings("thumbnail", WorkerSettingsRequest(options={"nao_existe": True}))

    with pytest.raises(InvalidWorkerSettingsError, match="objeto do runner"):
        service.update_settings("ner", WorkerSettingsRequest(options={"config": {"x": 1}}))


def test_a_retired_preset_is_refused_with_its_reason(service) -> None:
    """
    #122: ``granite_local`` was declared and cannot run on the documented Ollama.

    It is refused as retired, not as unknown: "não existe" reads as a typo, and the operator who
    still has the name in a settings row needs the reason and the name to use instead.
    """
    with pytest.raises(InvalidWorkerSettingsError, match="aposentado"):
        service.update_settings(
            "conflict-judge", WorkerSettingsRequest(engine_name="ollama_judge", preset="granite_local")
        )


def test_a_stale_row_with_a_retired_preset_falls_back_and_says_why(db_session, service) -> None:
    """
    The read path must survive what the write path refuses.

    A row written before the retirement is not a new mistake, and ``list_workers`` resolving it
    through ``describe_config`` would take the whole panel down with it. It resolves to the worker's
    own default instead, and the note carries the reason to the screen. The row is written directly
    because the write path is exactly what refuses it now.
    """
    db_session.add(
        WorkerSetting(
            worker_name="conflict-judge",
            engine_name="ollama_judge",
            preset="granite_local",
            db_batch_size=None,
            options={},
            updated_by="curador",
        )
    )
    db_session.flush()

    judge = next(worker for worker in service.list_workers().workers if worker.name == "conflict-judge")

    assert judge.settings.preset == "gemma_4b_local"
    assert judge.settings.config["model"] == "gemma4:e4b"
    assert judge.settings.note is not None
    assert "aposentado" in judge.settings.note
    assert "granite4.1:3b" in judge.settings.note


def test_an_active_rule_with_a_retired_preset_falls_back_too(db_session, service) -> None:
    """The other stale source is the active ``LLM_CHECK`` rule, and it must not 500 the panel either."""
    CleaningRepository(db_session).create_rule(
        CleaningRuleCreateDTO(
            rule_name="Revisão de título antiga",
            target_column="original_title",
            regex_pattern=".",
            replacement_string="",
            rule_kind="LLM_CHECK",
            engine_name="ollama_title_check",
            preset="granite_local",
        )
    )
    db_session.flush()

    validator = next(worker for worker in service.list_workers().workers if worker.name == "quality-validator")

    assert validator.settings.preset == "gemma_4b_local"
    assert validator.settings.config["model"] == "gemma4:e4b"
    assert validator.settings.note is not None
    assert "aposentado" in validator.settings.note


def test_the_thumbnail_worker_accepts_force(service) -> None:
    """A bucket that was down for an afternoon must not exclude those documents for good."""
    service.update_settings("thumbnail", WorkerSettingsRequest(options={"force": True}))

    thumbnail = next(worker for worker in service.list_workers().workers if worker.name == "thumbnail")
    assert thumbnail.settings.options == {"force": True}
    # With ``force`` the marked documents are pending again; without it the queue skips them.
    assert thumbnail.pending is not None


def test_the_engine_of_the_quality_validator_cannot_be_overridden_here(service) -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="LLM_CHECK"):
        service.update_settings("quality-validator", WorkerSettingsRequest(engine_name="ollama_title_check"))


def test_an_unknown_worker_is_a_named_error(service) -> None:
    with pytest.raises(WorkerNotFoundError):
        service.get_settings("nao-existe")


def test_the_queue_preview_counts_a_proposed_configuration_without_writing(
    service, db_session, generate_archive_doc, generate_typology
) -> None:
    """
    The cost of a change is readable before it is saved, and reading it saves nothing.

    The queue is keyed on the producer identity, so a new threshold re-reads the documents the old
    one settled — the archivist has to see that number first, and the preview must leave the
    settings row and its revisions exactly as they were.
    """
    generate_typology()
    config = TypologyRunnerConfig()
    identity = worker_typology.producer_identity(
        engine_name="deberta_typology",
        preset="cpu_local",
        columns_to_classify=list(config.columns_to_classify),
        confidence_threshold=config.confidence_threshold,
        typologies=TypologyRepository(db_session).get_active_typologies(),
        engine_kwargs={},
    )
    generate_archive_doc(original_title="Do produtor atual", execution_log={TYPOLOGY.key: identity})
    generate_archive_doc(original_title="Sem tipologia")

    assert service.preview_queue("typology", WorkerSettingsRequest()).pending == 1

    proposed = service.preview_queue("typology", WorkerSettingsRequest(options={"confidence_threshold": 0.6}))
    assert proposed.pending == 2

    assert service.get_settings("typology").overridden is False
    assert service.list_revisions("typology", limit=10, offset=0).total == 0


def test_the_preview_of_an_unmeasurable_queue_says_why(service) -> None:
    preview = service.preview_queue("conflict-judge", WorkerSettingsRequest())

    assert preview.pending is None
    assert preview.pending_reason


def test_the_panel_opens_the_stamp_into_a_breakdown(service, generate_archive_doc) -> None:
    """
    Issue #137: one "processed" number hid the legacy value, and for NER that was all of it.

    The row now says how many units a producer is actually named for, how many carry a value that
    names none, and how many have no record at all — the three the operator needs apart.
    """
    generate_archive_doc(original_title="Com produtor", execution_log={NER.key: "ab" * 32})
    generate_archive_doc(original_title="Legado", execution_log={NER.key: "DONE"})
    generate_archive_doc(original_title="Sem registro")

    ner = next(worker for worker in service.list_workers().workers if worker.name == "ner")

    assert ner.stamp_breakdown is not None
    assert ner.stamp_breakdown.fingerprinted == 1
    assert ner.stamp_breakdown.legacy == 1
    assert ner.stamp_breakdown.unrecorded == 1
    # ``processed`` is still there, now derived from the same aggregate instead of a second query.
    assert ner.processed == 2
    assert ner.failed == 0


def test_a_worker_whose_ledger_is_not_a_stamp_has_no_breakdown(service) -> None:
    """``thumbnail`` records its work in the storage URI, and a zero would read as "nothing done"."""
    thumbnail = next(worker for worker in service.list_workers().workers if worker.name == "thumbnail")

    assert thumbnail.stamp_breakdown is None
    assert thumbnail.processed == 0

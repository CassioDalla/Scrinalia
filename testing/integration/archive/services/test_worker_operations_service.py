"""The panel's read model and the settings writes, against the database."""

import pytest

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError, WorkerNotFoundError
from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository
from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO
from scrinalia.domains.archive.schemas.system_schema import WorkerSettingsRequest
from scrinalia.domains.archive.services.worker_operations_service import WorkerOperationsService
from scrinalia.domains.archive.workers import runner


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
            preset="granite_local",
        )
    )
    db_session.flush()

    with_rule = next(worker for worker in service.list_workers().workers if worker.name == "quality-validator")
    assert with_rule.settings.engine_name == "ollama_title_check"
    assert with_rule.settings.preset == "granite_local"
    assert with_rule.settings.config["model"] == "granite4.1:3b"


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

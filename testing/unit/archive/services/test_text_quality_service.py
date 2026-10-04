"""Unit tests of the text-quality service (repository mocked, no database)."""

from unittest.mock import MagicMock

import pytest

from memoria_curitibana.domains.archive.exceptions import InvalidParam, TextTemplateNotFoundError
from memoria_curitibana.domains.archive.schemas.text_quality_schema import (
    TemplateCreateCommand,
    TemplateDryRunRequest,
    TemplateUpdateCommand,
    TextTemplateDTO,
)
from memoria_curitibana.domains.archive.services.text_quality_service import TextQualityService
from memoria_curitibana.domains.archive.worker_stamp import QUALITY_VALIDATOR, TEXT_DEPENDENT_STAMPS

BLOCK = (
    "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do Planejamento, "
    "Urbanização e Fiscalização; - Parques, Bosques, Praças, Bairros e Ruas de Curitiba;"
)


@pytest.fixture
def repo() -> MagicMock:
    mock = MagicMock()
    mock.count_documents.return_value = 1000
    mock.find_documents_with_excerpt.return_value = []
    mock.requeue_documents.return_value = 0
    return mock


@pytest.fixture
def service(repo: MagicMock) -> TextQualityService:
    return TextQualityService(repo)


def _template(**overrides) -> TextTemplateDTO:
    data = {
        "template_id": 1,
        "text": "Registros Fotográficos -",
        "fingerprint": "a" * 64,
        "status": "APPROVED",
        "source": "HUMAN",
        "is_active": True,
    }
    data.update(overrides)
    return TextTemplateDTO(**data)


# ==========================================
# SUGGESTION
# ==========================================


def test_suggest_rejects_a_ratio_outside_the_unit_interval(service: TextQualityService) -> None:
    with pytest.raises(InvalidParam):
        service.suggest_templates(min_ratio=0)


def test_suggest_floor_is_relative_to_the_collection(service: TextQualityService, repo: MagicMock) -> None:
    """5% of 1000 documents is 50; 60 documents repeating the block must be proposed."""
    repo.iter_text_columns.return_value = [(f"doc-{index}", "scope_content", BLOCK) for index in range(60)]

    response = service.suggest_templates(min_ratio=0.05)

    assert response.documents_scanned == 1000
    assert len(response.candidates) == 1
    assert response.candidates[0].occurrence_count == 60
    persisted = repo.upsert_suggestions.call_args.args[0]
    assert persisted[0].text == BLOCK


def test_suggest_ignores_what_is_below_the_floor(service: TextQualityService, repo: MagicMock) -> None:
    repo.iter_text_columns.return_value = [(f"doc-{index}", "scope_content", BLOCK) for index in range(10)]

    response = service.suggest_templates(min_ratio=0.05)

    assert response.candidates == []
    repo.upsert_suggestions.assert_called_once_with([])


def test_suggest_skips_empty_values(service: TextQualityService, repo: MagicMock) -> None:
    repo.iter_text_columns.return_value = [("doc", "scope_content", None), ("doc", "scope_content", "   ")] * 100

    response = service.suggest_templates(min_ratio=0.01)

    assert response.candidates == []


# ==========================================
# CREATION AND EDIT
# ==========================================


def test_create_requeues_the_documents_the_excerpt_touches(service: TextQualityService, repo: MagicMock) -> None:
    repo.create_template.return_value = _template()
    repo.count_affected_documents.return_value = 42
    repo.find_documents_with_excerpt.return_value = ["doc-1", "doc-2"]
    repo.refresh_occurrence_count.return_value = _template(occurrence_count=42)
    repo.requeue_documents.return_value = 2

    template, requeued = service.create_template(TemplateCreateCommand(text="Registros Fotográficos -"))

    assert requeued == 2
    assert template.occurrence_count == 42
    # The evidence is measured, not guessed: the count comes from the SQL scan.
    repo.count_affected_documents.assert_called_once()
    assert repo.requeue_documents.call_args.args[1] == [stamp.key for stamp in TEXT_DEPENDENT_STAMPS]


def test_update_of_an_unknown_template_raises(service: TextQualityService, repo: MagicMock) -> None:
    repo.get_template.return_value = None

    with pytest.raises(TextTemplateNotFoundError):
        service.update_template(99, TemplateUpdateCommand(status="APPROVED"))


def test_update_that_does_not_change_the_effect_does_not_requeue(service: TextQualityService, repo: MagicMock) -> None:
    current = _template(reason="motivo antigo")
    updated = _template(reason="motivo novo")
    repo.get_template.return_value = current
    repo.update_template.return_value = updated
    repo.refresh_occurrence_count.return_value = updated

    _template_result, requeued = service.update_template(1, TemplateUpdateCommand(reason="motivo novo"))

    assert requeued == 0
    repo.requeue_documents.assert_not_called()


def test_approving_requeues_the_union_of_the_old_and_new_spellings(
    service: TextQualityService, repo: MagicMock
) -> None:
    pending = _template(status="SUGGESTED", is_active=False, text="antigo trecho")
    approved = _template(text="novo trecho")
    repo.get_template.return_value = pending
    repo.update_template.return_value = approved
    repo.count_affected_documents.return_value = 7
    repo.refresh_occurrence_count.return_value = approved
    repo.requeue_documents.return_value = 3

    _template_result, requeued = service.update_template(1, TemplateUpdateCommand(status="APPROVED"))

    assert requeued == 3
    matchers = repo.find_documents_with_excerpt.call_args.args[0]
    assert set(matchers) == {"antigo trecho", "novo trecho"}


def test_deactivate_requeues_because_the_effect_stops(service: TextQualityService, repo: MagicMock) -> None:
    approved = _template()
    deactivated = _template(is_active=False)
    repo.get_template.return_value = approved
    repo.update_template.return_value = deactivated
    repo.requeue_documents.return_value = 5

    _template_result, requeued = service.update_template(1, TemplateUpdateCommand(is_active=False))

    assert requeued == 5


def test_delete_undoes_the_effect_of_the_removed_excerpt(service: TextQualityService, repo: MagicMock) -> None:
    removed = _template()
    repo.delete_template.return_value = removed
    repo.find_documents_with_excerpt.return_value = ["doc-1"]
    repo.requeue_documents.return_value = 1

    snapshot, requeued = service.delete_template(1)

    assert snapshot is removed
    assert requeued == 1
    repo.requeue_documents.assert_called_once_with(["doc-1"], [stamp.key for stamp in TEXT_DEPENDENT_STAMPS])


def test_delete_of_an_unknown_template_raises(service: TextQualityService, repo: MagicMock) -> None:
    repo.delete_template.return_value = None

    with pytest.raises(TextTemplateNotFoundError):
        service.delete_template(99)


# ==========================================
# DRY RUN
# ==========================================


def test_dry_run_rejects_a_blank_excerpt(service: TextQualityService) -> None:
    with pytest.raises(InvalidParam):
        service.dry_run(TemplateDryRunRequest(text="   "))


def test_dry_run_forwards_the_normalized_matchers_and_the_action(service: TextQualityService, repo: MagicMock) -> None:
    service.dry_run(
        TemplateDryRunRequest(
            text="  trecho   repetido ",
            variants=["outra  grafia", ""],
            action="REPLACE",
            replacement="resumo",
            sample_limit=3,
        )
    )

    rules, columns = repo.dry_run.call_args.args[:2]
    assert rules[0].matchers == ("trecho repetido", "outra grafia")
    assert rules[0].replacement == "resumo"
    assert "original_title" in columns
    assert repo.dry_run.call_args.kwargs["sample_limit"] == 3


def test_dry_run_ignores_the_replacement_when_the_action_is_ignore(
    service: TextQualityService, repo: MagicMock
) -> None:
    service.dry_run(TemplateDryRunRequest(text="trecho", action="IGNORE", replacement="nao usado"))

    assert repo.dry_run.call_args.args[0][0].replacement == ""


def test_quality_validator_stamp_is_part_of_the_dependent_set() -> None:
    """The validator reads the effective text, so an excerpt change must re-queue it."""
    assert QUALITY_VALIDATOR in TEXT_DEPENDENT_STAMPS

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from scrinalia.domains.archive.exceptions import (
    CleaningRuleNotFoundError,
    InvalidLLMCheckEngineError,
    InvalidParam,
)
from scrinalia.domains.archive.models.governance import ArchiveCleaningRule
from scrinalia.domains.archive.schemas.cleaning_schema import (
    CleanableDocumentDTO,
    CleaningRuleCreateDTO,
    CleaningRuleDTO,
    DryRunRequestDTO,
)
from scrinalia.domains.archive.services.cleaning_service import CleaningService

# ==========================================
# FIXTURES (Test environment preparation)
# ==========================================


@pytest.fixture
def mock_repo():
    """Creates a fake repository so we do not hit the database."""
    repo = MagicMock()
    # Mock of the db attribute to test the commit in deactivate_rule
    repo.db = MagicMock()
    return repo


@pytest.fixture
def cleaning_service(mock_repo):
    """Injects the fake repository into our real service."""
    return CleaningService(mock_repo)


# ==========================================
# SCHEMA / DTO TESTS (Strict Validation)
# ==========================================
def test_dto_rejects_disallowed_column():
    """Guarantees that Pydantic blocks columns that are not in the Literal AllowedColumns."""
    with pytest.raises(ValidationError) as exc_info:
        CleaningRuleCreateDTO(
            rule_name="Regra Quebrada",
            target_column="coluna_inventada_que_nao_existe",  # Invalid # type: ignore
            regex_pattern=r"\bteste\b",
            replacement_string="",
        )
    assert "Input should be" in str(exc_info.value)


# ==========================================
# RULE CREATION TESTS (Regex Validation)
# ==========================================
def test_create_rule_success(cleaning_service, mock_repo):
    """Tests the happy path of creating a rule with a valid Regex."""
    dto = CleaningRuleCreateDTO(
        rule_name="Apagar Av",
        target_column="original_title",
        regex_pattern=r"\b(av\.?)\b",
        replacement_string="Avenida",
    )

    # Simulates the database return (the SQLAlchemy model)
    mock_rule = ArchiveCleaningRule(
        rule_id=1,
        rule_name=dto.rule_name,
        target_column=dto.target_column,
        regex_pattern=dto.regex_pattern,
        replacement_string=dto.replacement_string,
        is_active=True,
    )
    mock_repo.create_rule.return_value = mock_rule

    result = cleaning_service.create_cleaning_rule(dto)

    assert result.rule_id == 1
    assert result.is_active is True
    assert result.rule_name == "Apagar Av"
    mock_repo.create_rule.assert_called_once()


def test_create_rule_rejects_invalid_regex(cleaning_service):
    """Guarantees that the system raises the correct business exception if the Regex is broken."""
    dto = CleaningRuleCreateDTO(
        rule_name="Regra Bugada",
        target_column="original_title",
        regex_pattern=r"*[invalido",  # Syntactically broken Regex
        replacement_string="",
    )

    with pytest.raises(InvalidParam) as exc_info:
        cleaning_service.create_cleaning_rule(dto)

    assert "Sintaxe de Regex inválida" in str(exc_info.value)


# ==========================================
# RULE CREATION TESTS (the engine of an LLM_CHECK rule, issue #124)
# ==========================================
def llm_dto(**overrides) -> CleaningRuleCreateDTO:
    """An ``LLM_CHECK`` rule, which is the kind that carries an engine and a preset."""
    fields = {
        "rule_name": "Revisão de título por LLM",
        "target_column": "original_title",
        "regex_pattern": ".",
        "replacement_string": "",
        "rule_kind": "LLM_CHECK",
    }
    return CleaningRuleCreateDTO(**{**fields, **overrides})


def test_create_rule_refuses_an_engine_the_registry_does_not_have(cleaning_service, mock_repo):
    """
    The placeholder said ``ex.: ollama``, and ``ollama`` is not a registered engine.

    The refusal is a ``DomainException`` — the API owes a business status — and its sentence names
    the options, which is what turns the old trap (a saved rule whose engine kills the run) into a
    message at the door.
    """
    with pytest.raises(InvalidLLMCheckEngineError) as exc_info:
        cleaning_service.create_cleaning_rule(llm_dto(engine_name="ollama"))

    assert "ollama_title_check" in str(exc_info.value)
    mock_repo.create_rule.assert_not_called()


def test_create_rule_refuses_a_preset_the_registry_does_not_have(cleaning_service, mock_repo):
    with pytest.raises(InvalidLLMCheckEngineError) as exc_info:
        cleaning_service.create_cleaning_rule(llm_dto(engine_name="ollama_title_check", preset="gemma"))

    assert "gemma" in str(exc_info.value)
    mock_repo.create_rule.assert_not_called()


def test_create_rule_refuses_a_retired_preset_with_its_reason(cleaning_service, mock_repo):
    """The pair is validated through ``describe_config``, so a retired preset is refused too (#122)."""
    with pytest.raises(InvalidLLMCheckEngineError) as exc_info:
        cleaning_service.create_cleaning_rule(llm_dto(engine_name="ollama_title_check", preset="granite_local"))

    assert "aposentado" in str(exc_info.value)
    mock_repo.create_rule.assert_not_called()


def test_create_rule_accepts_the_registry_names(cleaning_service, mock_repo):
    mock_repo.create_rule.return_value = ArchiveCleaningRule(
        rule_id=7,
        rule_name="Revisão de título por LLM",
        target_column="original_title",
        regex_pattern=".",
        replacement_string="",
        rule_kind="LLM_CHECK",
        engine_name="ollama_title_check",
        preset="gemma_4b_local",
        is_active=True,
    )

    result = cleaning_service.create_cleaning_rule(llm_dto(engine_name="ollama_title_check", preset="gemma_4b_local"))

    assert result.engine_name == "ollama_title_check"
    mock_repo.create_rule.assert_called_once()


def test_an_empty_engine_stays_legal_and_means_the_default(cleaning_service, mock_repo):
    """The field must not become required: empty is the worker's documented fallback."""
    mock_repo.create_rule.return_value = ArchiveCleaningRule(
        rule_id=8,
        rule_name="Revisão de título por LLM",
        target_column="original_title",
        regex_pattern=".",
        replacement_string="",
        rule_kind="LLM_CHECK",
        is_active=True,
    )

    cleaning_service.create_cleaning_rule(llm_dto(engine_name=None, preset=None))

    mock_repo.create_rule.assert_called_once()


def test_a_preset_with_no_engine_is_validated_against_the_default(cleaning_service, mock_repo):
    """
    ``rule.preset`` with an empty engine is a preset *of the default engine*.

    The worker resolves ``rule.engine_name or "ollama_title_check"``, so the door has to validate the
    pair the run will actually resolve — otherwise a preset of another engine would be saved and the
    run would refuse it.
    """
    with pytest.raises(InvalidLLMCheckEngineError):
        cleaning_service.create_cleaning_rule(llm_dto(engine_name=None, preset="preset_fantasma"))

    mock_repo.create_rule.return_value = ArchiveCleaningRule(
        rule_id=9,
        rule_name="Revisão de título por LLM",
        target_column="original_title",
        regex_pattern=".",
        replacement_string="",
        rule_kind="LLM_CHECK",
        preset="gemma_4b_local",
        is_active=True,
    )
    cleaning_service.create_cleaning_rule(llm_dto(engine_name=None, preset="gemma_4b_local"))

    assert mock_repo.create_rule.call_count == 1


def test_the_pair_is_validated_whatever_the_rule_kind_is(cleaning_service, mock_repo):
    """A ``REWRITE`` rule carrying an engine is dead data, not a hole in the door."""
    with pytest.raises(InvalidLLMCheckEngineError):
        cleaning_service.create_cleaning_rule(
            llm_dto(rule_kind="REWRITE", engine_name="motor_que_nao_existe", preset=None)
        )

    mock_repo.create_rule.assert_not_called()


def test_a_rule_with_no_engine_at_all_is_never_validated(cleaning_service, mock_repo):
    """A ``REWRITE`` rule with neither field must not pay for the registry import at all."""
    mock_repo.create_rule.return_value = ArchiveCleaningRule(
        rule_id=10,
        rule_name="Apagar Av",
        target_column="original_title",
        regex_pattern=".",
        replacement_string="",
        is_active=True,
    )

    cleaning_service.create_cleaning_rule(
        CleaningRuleCreateDTO(
            rule_name="Apagar Av",
            target_column="original_title",
            regex_pattern=".",
            replacement_string="",
        )
    )

    mock_repo.create_rule.assert_called_once()


# ==========================================
# DRY-RUN TESTS (Simulation)
# ==========================================
def test_simulate_dry_run_with_matches(cleaning_service, mock_repo):
    """Tests whether the Regex replaces the text correctly in the mocked documents."""
    # Prepare the simulation DTO
    dto = DryRunRequestDTO(target_column="original_title", regex_pattern=r"\bav\b\.?", replacement_string="Avenida")

    # Mocks the repository to return 3 documents (2 with the anomaly, 1 clean)
    mock_repo.get_random_sample_for_dry_run.return_value = [
        CleanableDocumentDTO(description_id="BR_01", text="av. República Argentina"),
        CleanableDocumentDTO(description_id="BR_02", text="av Silva Jardim"),
        CleanableDocumentDTO(description_id="BR_03", text="Rua XV de Novembro"),  # Must not match
    ]

    result = cleaning_service.simulate_dry_run(dto)

    assert result.is_valid_regex is True
    assert result.matches_found == 2
    assert len(result.samples) == 2

    # Checks the exact substitutions
    assert result.samples[0].original_text == "av. República Argentina"
    assert result.samples[0].modified_text == "Avenida República Argentina"

    assert result.samples[1].original_text == "av Silva Jardim"
    assert result.samples[1].modified_text == "Avenida Silva Jardim"


def test_simulate_dry_run_invalid_regex(cleaning_service):
    """Tests whether the Dry-Run catches the Regex error and returns it in the DTO, without raising a 500 exception."""
    dto = DryRunRequestDTO(target_column="original_title", regex_pattern=r"(unclosed group", replacement_string="")

    result = cleaning_service.simulate_dry_run(dto)

    assert result.is_valid_regex is False
    assert "Sintaxe de Regex inválida" in result.error_message
    assert result.matches_found == 0


# ==========================================
# STATE CHANGE TESTS (Deactivate)
# ==========================================
def test_deactivate_rule_success(cleaning_service, mock_repo):
    """Tests whether the rule is deactivated through the repository, never committed by the service."""
    deactivated = CleaningRuleDTO(
        rule_id=99,
        rule_name="Regra Teste",
        is_active=False,
        target_column="original_title",
        regex_pattern=".",
        replacement_string="",
    )
    mock_repo.deactivate_rule.return_value = deactivated

    result = cleaning_service.deactivate_rule(99)

    # Checks whether the property was changed to False
    assert result.is_active is False
    # The service delegates to the repository; it never commits on its own.
    mock_repo.deactivate_rule.assert_called_once_with(99)
    mock_repo.db.commit.assert_not_called()


def test_deactivate_rule_not_found(cleaning_service, mock_repo):
    """Tests whether a domain error is raised when the rule does not exist in the DB."""
    mock_repo.deactivate_rule.return_value = None

    with pytest.raises(CleaningRuleNotFoundError) as exc_info:
        cleaning_service.deactivate_rule(999)

    assert "Regra 999 não encontrada" in str(exc_info.value)


def test_activate_rule_success(cleaning_service, mock_repo):
    """Reactivation is the way back deactivation promised; the service still never commits."""
    activated = CleaningRuleDTO(
        rule_id=99,
        rule_name="Regra Teste",
        is_active=True,
        target_column="original_title",
        regex_pattern=".",
        replacement_string="",
    )
    mock_repo.activate_rule.return_value = activated

    result = cleaning_service.activate_rule(99)

    assert result.is_active is True
    mock_repo.activate_rule.assert_called_once_with(99)
    mock_repo.db.commit.assert_not_called()


def test_activate_rule_not_found(cleaning_service, mock_repo):
    mock_repo.activate_rule.return_value = None

    with pytest.raises(CleaningRuleNotFoundError) as exc_info:
        cleaning_service.activate_rule(999)

    assert "Regra 999 não encontrada" in str(exc_info.value)

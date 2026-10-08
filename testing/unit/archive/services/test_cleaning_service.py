from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from scrinalia.domains.archive.exceptions import CleaningRuleNotFoundError, InvalidParam
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

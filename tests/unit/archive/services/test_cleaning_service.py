from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from domains.archive.exceptions import InvalidParam
from domains.archive.models.governance import ArchiveCleaningRule
from domains.archive.schemas.cleaning_schema import (
    CleaningRuleCreateDTO,
    DryRunRequestDTO,
)
from domains.archive.services.cleaning_service import CleaningService


# ==========================================
# FIXTURES (Preparação do ambiente de teste)
# ==========================================
@pytest.fixture
def mock_repo():
    """Cria um repositório falso para não batermos no banco de dados."""
    repo = MagicMock()
    # Mock do atributo db para testarmos o commit no deactivate_rule
    repo.db = MagicMock()
    return repo


@pytest.fixture
def cleaning_service(mock_repo):
    """Injeta o repositório falso no nosso serviço real."""
    return CleaningService(mock_repo)


class MockArchiveDocument:
    """Classe simples para simular os documentos retornados pelo Repositório."""

    def __init__(self, description_id, text):
        self.description_id = description_id
        self.original_title = text  # Simularemos a coluna 'original_title'


# ==========================================
# TESTES DE SCHEMAS / DTOs (Validação Estrita)
# ==========================================
def test_dto_rejeita_coluna_nao_permitida():
    """Garante que o Pydantic bloqueia colunas que não estão no Literal AllowedColumns."""
    with pytest.raises(ValidationError) as exc_info:
        CleaningRuleCreateDTO(
            rule_name="Regra Quebrada",
            target_column="coluna_inventada_que_nao_existe",  # Invalido # type: ignore
            regex_pattern=r"\bteste\b",
            replacement_string="",
        )
    assert "Input should be" in str(exc_info.value)


# ==========================================
# TESTES DE CRIAÇÃO DE REGRA (Validação Regex)
# ==========================================
def test_create_rule_sucesso(cleaning_service, mock_repo):
    """Testa o fluxo feliz de criar uma regra com um Regex válido."""
    dto = CleaningRuleCreateDTO(
        rule_name="Apagar Av",
        target_column="original_title",
        regex_pattern=r"\b(av\.?)\b",
        replacement_string="Avenida",
    )

    # Simula o retorno do banco de dados (A model do SQLAlchemy)
    mock_rule = ArchiveCleaningRule(
        rule_id=1,
        rule_name=dto.rule_name,
        target_column=dto.target_column,
        regex_pattern=dto.regex_pattern,
        replacement_string=dto.replacement_string,
        is_active=True,
    )
    mock_repo.create_rule.return_value = mock_rule

    resultado = cleaning_service.create_cleaning_rule(dto)

    assert resultado.rule_id == 1
    assert resultado.is_active is True
    assert resultado.rule_name == "Apagar Av"
    mock_repo.create_rule.assert_called_once()


def test_create_rule_rejeita_regex_invalido(cleaning_service):
    """Garante que o sistema lança a exceção de negócio correta se o Regex estiver quebrado."""
    dto = CleaningRuleCreateDTO(
        rule_name="Regra Bugada",
        target_column="original_title",
        regex_pattern=r"*[invalido",  # Regex sintaticamente quebrado
        replacement_string="",
    )

    with pytest.raises(InvalidParam) as exc_info:
        cleaning_service.create_cleaning_rule(dto)

    assert "Sintaxe de Regex inválida" in str(exc_info.value)


# ==========================================
# TESTES DE DRY-RUN (Simulação)
# ==========================================
def test_simulate_dry_run_com_matches(cleaning_service, mock_repo):
    """Testa se o Regex substitui o texto corretamente nos documentos mockados."""
    # Prepara o DTO de simulação
    dto = DryRunRequestDTO(target_column="original_title", regex_pattern=r"\bav\b\.?", replacement_string="Avenida")

    # Moca o repositório para devolver 3 documentos (2 com a anomalia, 1 limpo)
    mock_repo.get_random_sample_for_dry_run.return_value = [
        MockArchiveDocument("BR_01", "av. República Argentina"),
        MockArchiveDocument("BR_02", "av Silva Jardim"),
        MockArchiveDocument("BR_03", "Rua XV de Novembro"),  # Não deve dar match
    ]

    resultado = cleaning_service.simulate_dry_run(dto)

    assert resultado.is_valid_regex is True
    assert resultado.matches_found == 2
    assert len(resultado.samples) == 2

    # Verifica as substituições exatas
    assert resultado.samples[0].original_text == "av. República Argentina"
    assert resultado.samples[0].modified_text == "Avenida República Argentina"

    assert resultado.samples[1].original_text == "av Silva Jardim"
    assert resultado.samples[1].modified_text == "Avenida Silva Jardim"


def test_simulate_dry_run_regex_invalido(cleaning_service):
    """Testa se o Dry-Run captura o erro de Regex e devolve no DTO, sem estourar exceção 500."""
    dto = DryRunRequestDTO(target_column="original_title", regex_pattern=r"(unclosed group", replacement_string="")

    resultado = cleaning_service.simulate_dry_run(dto)

    assert resultado.is_valid_regex is False
    assert "Sintaxe de Regex inválida" in resultado.error_message
    assert resultado.matches_found == 0


# ==========================================
# TESTES DE MUDANÇA DE ESTADO (Desativar)
# ==========================================
def test_deactivate_rule_sucesso(cleaning_service, mock_repo):
    """Testa se a regra é desativada e o commit é acionado."""
    # Instancia a regra com is_active=True
    mock_rule = ArchiveCleaningRule(
        rule_id=99,
        rule_name="Regra Teste",
        is_active=True,
        target_column="original_title",
        regex_pattern=".",
        replacement_string="",
    )

    mock_repo.get_rule_by_id.return_value = mock_rule

    resultado = cleaning_service.deactivate_rule(99)

    # Verifica se a propriedade foi alterada para False
    assert resultado.is_active is False
    # Verifica se a nossa "preguiça genial" acionou o commit no DB
    mock_repo.db.commit.assert_called_once()


def test_deactivate_rule_nao_encontrada(cleaning_service, mock_repo):
    """Testa se lança ValueError quando a regra não existe no DB."""
    mock_repo.get_rule_by_id.return_value = None

    with pytest.raises(ValueError) as exc_info:
        cleaning_service.deactivate_rule(999)

    assert "Regra 999 não encontrada" in str(exc_info.value)

from unittest.mock import MagicMock, patch

import pytest

from domains.archive.models.governance import ArchiveCleaningRule
from domains.archive.workers.worker_cleaning_regex import execute


# ==========================================
# FIXTURES E MOCKS
# ==========================================
class MockDocument:
    """Simula um documento retornado pelo banco de dados."""

    def __init__(self, description_id, text, execution_log=None):
        self.description_id = description_id
        self.original_title = text
        self.execution_log = execution_log


@pytest.fixture
def mock_db():
    """Mock da Sessão do SQLAlchemy."""
    return MagicMock()


@pytest.fixture
def mock_repo():
    """Mock do Repositório injetado no Worker."""
    with patch("domains.archive.workers.worker_cleaning_regex.CleaningRepository") as MockRepoClass:
        yield MockRepoClass.return_value


@pytest.fixture
def mock_flag_modified():
    """Mock da função flag_modified do SQLAlchemy para não dar erro sem mapeamento real."""
    with patch("domains.archive.workers.worker_cleaning_regex.flag_modified") as mock_flag:
        yield mock_flag


# ==========================================
# TESTES
# ==========================================
def test_worker_encerra_se_nao_houver_regras(mock_db, mock_repo):
    """Garante que o Worker não faz queries inúteis se não houver regras ativas."""
    mock_repo.get_active_rules.return_value = []

    execute(mock_db)

    mock_repo.get_unprocessed_documents_for_rule.assert_not_called()
    mock_db.commit.assert_not_called()


def test_worker_aplica_regra_com_sucesso(mock_db, mock_repo, mock_flag_modified):
    """Testa o fluxo perfeito (Caminho Feliz): Limpa, carimba o JSONB e comita."""
    # 1. Prepara a regra ativa
    rule = ArchiveCleaningRule(
        rule_id=5,
        rule_name="Limpa Av",
        target_column="original_title",
        regex_pattern=r"\bav\b\.?",
        replacement_string="Avenida",
    )
    mock_repo.get_active_rules.return_value = [rule]

    # 2. Prepara os documentos mockados
    doc_sujo = MockDocument("BR_01", "av. Paulista", execution_log=None)
    doc_limpo = MockDocument("BR_02", "Avenida Brasil", execution_log={"outra_regra": "DONE"})

    # 3. O side_effect simula o loop do while: Primeiro devolve 2 docs, depois devolve vazio para encerrar o lote
    mock_repo.get_unprocessed_documents_for_rule.side_effect = [
        [doc_sujo, doc_limpo],
        [],  # Encerra o While True
    ]

    # Executa o Worker
    execute(mock_db)

    # Verifica Documento 1 (Deveria ser modificado e carimbado)
    assert doc_sujo.original_title == "Avenida Paulista"
    assert doc_sujo.execution_log == {"cleaning_rule_5": "DONE"}

    # Verifica Documento 2 (Não modifica o texto, preserva logs antigos e adiciona o novo)
    assert doc_limpo.original_title == "Avenida Brasil"  # Intacto
    assert doc_limpo.execution_log == {"outra_regra": "DONE", "cleaning_rule_5": "DONE"}

    # Verifica se o banco foi salvo
    mock_db.commit.assert_called_once()
    assert mock_flag_modified.call_count == 2


def test_worker_pula_regra_com_regex_invalido(mock_db, mock_repo):
    """Garante que se uma regra tiver um Regex quebrado no banco, o Worker pula sem explodir."""
    rule_quebrada = ArchiveCleaningRule(
        rule_id=1, rule_name="Erro", target_column="original_title", regex_pattern=r"*[", replacement_string=""
    )
    rule_boa = ArchiveCleaningRule(
        rule_id=2, rule_name="Boa", target_column="original_title", regex_pattern=r"teste", replacement_string=""
    )

    mock_repo.get_active_rules.return_value = [rule_quebrada, rule_boa]

    # Simula que não há documentos para a regra boa só para encerrar rápido
    mock_repo.get_unprocessed_documents_for_rule.return_value = []

    execute(mock_db)

    # Ele deve ter tentado processar a regra 2 (Boa), o que prova que não travou na regra 1
    mock_repo.get_unprocessed_documents_for_rule.assert_called_once_with(
        rule_id=2, target_column="original_title", limit=500
    )


def test_worker_faz_rollback_em_caso_de_erro_de_banco(mock_db, mock_repo, mock_flag_modified):
    """Se houver erro de constraint/conexão no meio do lote, deve fazer rollback e sair do loop infinito."""
    rule = ArchiveCleaningRule(
        rule_id=10, rule_name="Regra X", target_column="original_title", regex_pattern="x", replacement_string="y"
    )
    mock_repo.get_active_rules.return_value = [rule]

    doc = MockDocument("BR_01", "x")
    mock_repo.get_unprocessed_documents_for_rule.return_value = [doc]

    # Força um erro no momento do commit (Ex: Queda de rede, Deadlock)
    mock_db.commit.side_effect = Exception("Deadlock detectado")

    execute(mock_db)

    # Deve ter feito o rollback para não corromper o banco
    mock_db.rollback.assert_called_once()

    # E muito importante: Ele não pode ter ficado preso num loop infinito `While True`
    mock_repo.get_unprocessed_documents_for_rule.assert_called_once()

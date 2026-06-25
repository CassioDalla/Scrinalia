from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.workers import worker_typology


class MockArchiveDocument:
    """Dublê ultraleve simulando um documento do SQLAlchemy para os Testes Unitários."""

    def __init__(self, description_id: str, title: str, content: str | None = None):
        self.description_id = description_id
        self.original_title = title
        self.scope_content = content
        self.typology_id = None
        self.execution_log = None


# ==========================================
# TESTES DE ORQUESTRAÇÃO DO WORKER DE TIPOLOGIA
# ==========================================


def test_worker_typology_unitario_fluxo_ideal(mocker: MockerFixture) -> None:
    """Cenário Bom: Textos são concatenados ignorando nulos, IA classifica e doc é atualizado."""
    mock_db = mocker.Mock(spec=Session)

    # 1. Mocks das Classes/Funções Externas no escopo do Worker
    mock_repo_class = mocker.patch("domains.archive.workers.worker_typology.TypologyRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_typology.get_engine")
    mock_flag_modified = mocker.patch("domains.archive.workers.worker_typology.flag_modified")

    # 2. Configurações dos Retornos (Falsificando o BD e a IA)
    mock_repo = mock_repo_class.return_value
    mock_repo.get_active_typologies.return_value = {"Contrato": 1}

    mock_classifier_engine = mock_get_engine.return_value
    # A IA do HuggingFace/ZeroShot retorna uma lista com o formato: [{"labels": [...], "scores": [...]}]
    mock_classifier_engine.classify.return_value = [{"labels": ["Contrato"], "scores": [0.95]}]

    # 3. Simula a fila do banco de dados (1 documento na 1ª volta, quebra o laço na 2ª)
    # Mandamos o content como None para testar se ele ignora o Nulo e não concatena lixo
    doc_teste = MockArchiveDocument("doc-1", "Contrato de Prestação de Serviços", None)
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # 4. Execução
    worker_typology.execute(
        db=mock_db,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    # 5. Verificações de IA
    mock_classifier_engine.classify.assert_called_once()
    args, _ = mock_classifier_engine.classify.call_args
    # Confirma se as colunas foram limpas, unidas com ponto e ignorou o campo "scope_content" (None)
    assert args[0] == ["Contrato de Prestação de Serviços"]

    # 6. Verificações de Persistência
    assert doc_teste.typology_id == 1
    assert doc_teste.execution_log["worker_typology_classifier_v1"] == "DONE"  # type: ignore

    mock_flag_modified.assert_called_once_with(doc_teste, "execution_log")
    mock_db.commit.assert_called_once()


def test_worker_typology_ignora_textos_vazios(mocker: MockerFixture) -> None:
    """Cenário Limite: Documentos sem texto útil devem ser pulados na IA, mas carimbados no BD."""
    mock_db = mocker.Mock(spec=Session)

    mocker.patch("domains.archive.workers.worker_typology.TypologyRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_typology.get_engine")
    mock_flag_modified = mocker.patch("domains.archive.workers.worker_typology.flag_modified")

    # Documento onde tudo está vazio
    doc_vazio = MockArchiveDocument("doc-2", "   ", None)
    mock_db.scalars.return_value.all.side_effect = [[doc_vazio], []]

    worker_typology.execute(db=mock_db)

    # A IA não pode ter sido chamada (poupa processamento)
    mock_get_engine.return_value.classify.assert_not_called()

    # O carimbo deve ter sido aplicado para o Worker não entrar em loop amanhã
    assert doc_vazio.execution_log["worker_typology_classifier_v1"] == "DONE"  # type: ignore
    mock_flag_modified.assert_called_once()


def test_worker_typology_falha_na_ia_faz_rollback(mocker: MockerFixture) -> None:
    """Cenário Ruim: Se o motor Zero-Shot der erro de memória, a transação aborta e faz rollback."""
    mock_db = mocker.Mock(spec=Session)

    mocker.patch("domains.archive.workers.worker_typology.TypologyRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_typology.get_engine")

    doc_teste = MockArchiveDocument("doc-3", "Texto super complexo", "Muitas palavras")
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # Forçamos o motor NLP a explodir
    mock_get_engine.return_value.classify.side_effect = Exception("Out of Memory na GPU")

    worker_typology.execute(db=mock_db)

    # O rollback deve ter sido chamado para proteger a transação do banco
    mock_db.rollback.assert_called()

    # O carimbo não deve ter sido aplicado, permitindo nova tentativa futuramente
    assert doc_teste.execution_log is None

from unittest.mock import MagicMock, patch

from domains.archive.workers.worker_ner import execute


class MockArchiveDocument:
    """Dublê ultraleve simulando um documento do SQLAlchemy para os Testes Unitários."""

    def __init__(self, description_id, title, content=""):
        self.description_id = description_id
        self.original_title = title
        self.admin_bio_history = None
        self.provenance = None
        self.scope_content = content
        self.execution_log = None


# ==========================================
# 1. TESTES UNITÁRIOS (Lógica e Tratamento de Erros)
# ==========================================


@patch("domains.archive.workers.worker_ner.get_engine")
@patch("domains.archive.workers.worker_ner.repository")
def test_worker_ner_unitario_fluxo_ideal(mock_repo, mock_get_engine, mock_ner_engine):
    """Cenário Bom: Textos são concatenados, IA extrai e repositório salva."""
    mock_get_engine.return_value = mock_ner_engine
    mock_repo.get_ner_synonyms_rules.return_value = []
    mock_repo.get_or_create_entities.return_value = [101]

    # Simulamos o banco de dados
    mock_db = MagicMock()
    doc_teste = MockArchiveDocument("doc-1", "Ofício", "Conteúdo sobre obras.")

    # O side_effect quebra o laço 'while True': devolve o documento na 1ª volta e vazio na 2ª.
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # Execução
    execute(db=mock_db, engine_name="spacy_ner")

    # Verificações
    mock_ner_engine.extract.assert_called_once()
    args, _ = mock_ner_engine.extract.call_args
    # Confirma se as colunas foram limpas e unidas com ponto e espaço
    assert args[0] == ["Ofício. Conteúdo sobre obras."]

    # Verifica se os vínculos foram comandados ao repositório
    mock_repo.link_description_relationships.assert_called_once_with(
        mock_db, description_id="doc-1", entity_ids=[101], tag_ids=[]
    )

    # O carimbo foi aplicado em memória?
    assert doc_teste.execution_log["worker_ner_v1"] == "DONE"  # type: ignore
    mock_db.commit.assert_called_once()


@patch("domains.archive.workers.worker_ner.get_engine")
@patch("domains.archive.workers.worker_ner.repository")
def test_worker_ner_ignora_textos_vazios(mock_repo, mock_get_engine, mock_ner_engine):
    """Cenário Bom: Se o documento só tem espaços, carimba como DONE e pula a IA."""
    mock_get_engine.return_value = mock_ner_engine
    mock_db = MagicMock()

    doc_vazio = MockArchiveDocument("doc-2", "   ", "")
    mock_db.scalars.return_value.all.side_effect = [[doc_vazio], []]

    execute(db=mock_db)

    # A IA não deve ter sido acionada para não gastar processamento
    mock_ner_engine.extract.assert_not_called()

    # Mas o documento DEVE ser carimbado para sair da fila
    assert doc_vazio.execution_log["worker_ner_v1"] == "DONE"  # type: ignore


@patch("domains.archive.workers.worker_ner.get_engine")
@patch("domains.archive.workers.worker_ner.repository")
def test_worker_ner_falha_na_ia_faz_rollback(mock_repo, mock_get_engine, mock_ner_engine):
    """Cenário Ruim: Se o spaCy estourar a memória, a transação aborta e o laço quebra."""
    mock_get_engine.return_value = mock_ner_engine
    mock_db = MagicMock()

    doc_teste = MockArchiveDocument("doc-3", "Texto válido")
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # Forçamos o motor NLP a explodir
    mock_ner_engine.extract.side_effect = Exception("Out of Memory")

    execute(db=mock_db)

    # O rollback deve ter sido chamado
    mock_db.rollback.assert_called()
    # O carimbo NÃO deve ser aplicado, pois o lote inteiro falhou na inferência
    assert doc_teste.execution_log is None


@patch("domains.archive.workers.worker_ner.get_engine")
@patch("domains.archive.workers.worker_ner.repository")
def test_worker_ner_falha_no_repositorio_carimba_erro(mock_repo, mock_get_engine, mock_ner_engine):
    """Cenário Ruim (Anti-Loop): A IA funciona, mas o banco recusa a inserção. Carimba com ERROR."""
    mock_get_engine.return_value = mock_ner_engine
    mock_db = MagicMock()

    doc_teste = MockArchiveDocument("doc-4", "Texto válido")
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # Forçamos uma falha de integridade relacional na hora de gravar as entidades
    mock_repo.get_or_create_entities.side_effect = Exception("Erro de Foreign Key")

    execute(db=mock_db)

    # A blindagem funcionou?
    assert doc_teste.execution_log["worker_ner_v1"] == "ERROR"  # type: ignore

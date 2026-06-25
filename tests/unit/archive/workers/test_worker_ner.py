from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.workers import worker_ner


class MockArchiveDocument:
    """Dublê ultraleve simulando um documento do SQLAlchemy para os Testes Unitários."""

    def __init__(self, description_id: str, title: str, content: str = ""):
        self.description_id = description_id
        self.original_title = title
        self.admin_bio_history = None
        self.provenance = None
        self.scope_content = content
        self.execution_log = None


# ==========================================
# 1. TESTES DO HELPER DE LIMPEZA
# ==========================================


def test_clean_raw_text_remove_urls_e_emails():
    """Garante que a função auxiliar limpa ruídos de web corretamente."""
    texto_sujo = "Visite http://site.com ou www.teste.com e mande email para admin@gov.br. Texto limpo."
    resultado = worker_ner._clean_raw_text(texto_sujo)

    assert resultado == "Visite  ou  e mande email para  Texto limpo."


def test_clean_raw_text_vazio():
    assert worker_ner._clean_raw_text(None) == ""  # type: ignore
    assert worker_ner._clean_raw_text("   ") == ""


# ==========================================
# 2. TESTES DE ORQUESTRAÇÃO DO WORKER
# ==========================================


def test_worker_ner_unitario_fluxo_ideal(mocker: MockerFixture) -> None:
    """Cenário Bom: Textos são concatenados, IA extrai e repositório salva."""
    mock_db = mocker.Mock(spec=Session)

    # 1. Mocks das Classes/Funções Externas
    mock_repo_class = mocker.patch("domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_ner.get_engine")
    mock_flag_modified = mocker.patch("domains.archive.workers.worker_ner.flag_modified")

    # 2. Configurando o Repositório e a IA
    mock_repo = mock_repo_class.return_value
    mock_repo.get_ner_synonyms_rules.return_value = []
    mock_repo.get_or_create_entities.return_value = [101]

    mock_ner_engine = mock_get_engine.return_value
    # Retorna uma lista de DTOs simulada para 1 documento
    mock_ner_engine.extract.return_value = [[mocker.Mock()]]

    # 3. Simula a fila do banco de dados (1 documento na primeira volta, vazio na segunda para quebrar o while)
    doc_teste = MockArchiveDocument("doc-1", "Ofício", "Conteúdo sobre obras.")
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # 4. Execução
    worker_ner.execute(db=mock_db, engine_name="spacy_ner")

    # 5. Verificações de IA
    mock_ner_engine.extract.assert_called_once()
    args, _ = mock_ner_engine.extract.call_args
    # Confirma se as colunas foram limpas e unidas com ponto e espaço
    assert args[0] == ["Ofício. Conteúdo sobre obras."]

    # 6. Verificações de Persistência (usando a nova cardinalidade do Repositório)
    mock_repo.link_entities_to_document.assert_called_once_with(description_id="doc-1", entity_ids=[101])

    # O carimbo de sucesso foi aplicado na memória do documento?
    assert doc_teste.execution_log["worker_ner_v1"] == "DONE"  # type: ignore
    mock_flag_modified.assert_called_once_with(doc_teste, "execution_log")
    mock_db.commit.assert_called_once()


def test_worker_ner_ignora_textos_vazios(mocker: MockerFixture) -> None:
    """Cenário Bom: Se o documento só tem espaços ou URLs, carimba como DONE e pula a IA."""
    mock_db = mocker.Mock(spec=Session)

    mock_repo_class = mocker.patch("domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_ner.get_engine")
    mock_flag_modified = mocker.patch("domains.archive.workers.worker_ner.flag_modified")

    mock_ner_engine = mock_get_engine.return_value

    # Documento que, após remover o email, fica vazio
    doc_vazio = MockArchiveDocument("doc-2", "   ", "contato@email.com")
    mock_db.scalars.return_value.all.side_effect = [[doc_vazio], []]

    worker_ner.execute(db=mock_db)

    # A IA NÃO deve ter sido acionada para não gastar processamento à toa
    mock_ner_engine.extract.assert_not_called()

    # Mas o documento DEVE ser carimbado para não entrar em loop infinito na fila
    assert doc_vazio.execution_log["worker_ner_v1"] == "DONE"  # type: ignore
    mock_flag_modified.assert_called_once()


def test_worker_ner_falha_na_ia_faz_rollback(mocker: MockerFixture) -> None:
    """Cenário Ruim: Se o spaCy estourar a memória (Exception), a transação aborta e o laço quebra."""
    mock_db = mocker.Mock(spec=Session)

    mocker.patch("domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_ner.get_engine")

    doc_teste = MockArchiveDocument("doc-3", "Texto válido para forçar a IA a rodar")
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # Forçamos o motor NLP a explodir
    mock_get_engine.return_value.extract.side_effect = Exception("Out of Memory")

    worker_ner.execute(db=mock_db)

    # O rollback deve ter sido chamado para proteger o banco
    mock_db.rollback.assert_called()

    # O carimbo NÃO deve ser aplicado (permanece None), pois o lote inteiro falhou na inferência
    assert doc_teste.execution_log is None


def test_worker_ner_falha_no_repositorio_carimba_erro(mocker: MockerFixture) -> None:
    """Cenário Ruim (Resiliência): A IA funciona, mas o banco recusa a inserção. Carimba com ERROR e avança."""
    mock_db = mocker.Mock(spec=Session)

    mock_repo_class = mocker.patch("domains.archive.workers.worker_ner.EntityRepository")
    mock_get_engine = mocker.patch("domains.archive.workers.worker_ner.get_engine")
    mock_flag_modified = mocker.patch("domains.archive.workers.worker_ner.flag_modified")

    # Simulamos que a IA encontrou 1 entidade
    mock_get_engine.return_value.extract.return_value = [[mocker.Mock()]]

    doc_teste = MockArchiveDocument("doc-4", "Texto válido")
    mock_db.scalars.return_value.all.side_effect = [[doc_teste], []]

    # Forçamos uma falha estrutural (ex: erro de Foreign Key) na hora de gravar a entidade
    mock_repo_class.return_value.get_or_create_entities.side_effect = Exception("DB Constraints Failed")

    worker_ner.execute(db=mock_db)

    # A blindagem anti-loop infinito funcionou? O documento DEVE ser carimbado com ERROR.
    assert doc_teste.execution_log["worker_ner_v1"] == "ERROR"  # type: ignore
    mock_flag_modified.assert_called_once()

    # O batch avança e faz o commit dos outros (ou do próprio erro no log)
    mock_db.commit.assert_called()

from unittest.mock import Mock

from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from core.crud import gold_crud
from scripts.gold import worker_ner

# ==========================================
# 1. TESTES UNITÁRIOS DE LÓGICA PURA (NLP)
# ==========================================


def test_extrair_entidades_texto_sucesso(mocker: MockerFixture) -> None:
    """Testa se entidades legítimas são capturadas, limpas e padronizadas com Title Case."""
    # Simula objetos internos estruturais do spaCy (.text e .label_)
    mock_ent_per = mocker.Mock()
    mock_ent_per.text = "david carneiro"
    mock_ent_per.label_ = "PER"
    mock_ent_per.ent_id_ = ""

    mock_ent_loc = mocker.Mock()
    mock_ent_loc.text = "rua brigadeiro franco"
    mock_ent_loc.label_ = "LOC"
    mock_ent_loc.ent_id_ = ""

    mock_doc = mocker.Mock()
    mock_doc.ents = [mock_ent_per, mock_ent_loc]

    mock_nlp_engine = mocker.Mock(return_value=mock_doc)

    resultado = worker_ner.extract_entities_text("Texto", mock_nlp_engine)

    assert len(resultado) == 2
    # Valida a transformação para Title Case (.title())
    assert resultado[0].name == "David Carneiro"
    assert resultado[0].entity_type == "PER"
    assert resultado[1].name == "Rua Brigadeiro Franco"
    assert resultado[1].entity_type == "LOC"


def test_extrair_entidades_texto_data_quality_filtra_lixo(mocker: MockerFixture) -> None:
    """Garante que a esteira descarte ruídos textuais (strings muito curtas ou excessivamente longas)."""
    mock_ent_curta = mocker.Mock()
    mock_ent_curta.text = "X"  # Apenas 1 caractere (Lixo de OCR/Digitação)
    mock_ent_curta.label_ = "LOC"
    mock_ent_curta.ent_id_ = ""

    mock_ent_longa = mocker.Mock()
    mock_ent_longa.text = "A" * 155  # Passa do limite de 150 caracteres
    mock_ent_longa.label_ = "ORG"
    mock_ent_longa.ent_id_ = ""

    mock_doc = mocker.Mock()
    mock_doc.ents = [mock_ent_curta, mock_ent_longa]

    mock_nlp_engine = mocker.Mock(return_value=mock_doc)

    resultado = worker_ner.extract_entities_text("Texto...", mock_nlp_engine)

    # Ambas as entidades ferem a política de Data Quality e devem sumir
    assert len(resultado) == 0


# ==========================================
# 2. TESTES DE INTEGRALIDADE DO WORKER (ORQUESTRADOR)
# ==========================================


def test_executar_worker_ner_fluxo_completo(mocker: MockerFixture) -> None:
    """Testa o caminho feliz: lê documento pendente, extrai entidades, salva e carimba checkpoint."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_ner, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.execute.return_value.fetchall.return_value = []

    # Cria documento Ouro simulado necessitando do spaCy
    doc_gold_fake = Mock()
    doc_gold_fake.description_id = "gold-dossie-1"
    doc_gold_fake.original_title = "Título Legal"
    doc_gold_fake.admin_bio_history = "Histórico do produtor David Carneiro."
    doc_gold_fake.provenance = "Coleção Particular."
    doc_gold_fake.scope_content = "Conteúdo rico de Curitiba."

    mock_query = Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_gold_fake]

    # Isola o teste do comportamento real do spaCy injetando um DTO falso controlado
    fake_dto = Mock()
    mocker.patch.object(worker_ner, "extract_entities_text", return_value=[fake_dto])

    # Mocks das chamadas de persistência do CRUD
    mock_get_or_create = mocker.patch.object(gold_crud, "get_or_create_entities", return_value=[777])
    mock_link = mocker.patch.object(gold_crud, "link_description_relationships")
    mock_carimbar = mocker.patch.object(gold_crud, "stamp_ai_execution")

    worker_ner.executar_worker_ner()

    # Verifica se os dados fluíram corretamente pelas pontes relacionais
    mock_get_or_create.assert_called_once_with(mock_db, [fake_dto])
    mock_link.assert_called_once_with(mock_db, description_id="gold-dossie-1", entity_ids=[777], tag_ids=[])
    # Garante que o passaporte foi carimbado para tirar o documento da fila
    mock_carimbar.assert_called_once_with(mock_db, "gold-dossie-1", "ner_spacy")
    mock_db.commit.assert_called_once()


def test_executar_worker_ner_vazio_obrigatoriamente_carimba_log(mocker: MockerFixture) -> None:
    """Garante que se o documento não possuir entidades, o checkpoint é gravado mesmo assim."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_ner, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.execute.return_value.fetchall.return_value = []

    doc_gold_fake = Mock()
    doc_gold_fake.description_id = "gold-vazio"
    doc_gold_fake.original_title = None
    doc_gold_fake.admin_bio_history = None
    doc_gold_fake.provenance = None
    doc_gold_fake.scope_content = None

    mock_query = Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_gold_fake]

    # Força o spaCy a retornar uma lista vazia (nenhuma entidade encontrada)
    mocker.patch.object(worker_ner, "extract_entities_text", return_value=[])

    mock_get_or_create = mocker.patch.object(gold_crud, "get_or_create_entities")
    mock_link = mocker.patch.object(gold_crud, "link_description_relationships")
    mock_carimbar = mocker.patch.object(gold_crud, "stamp_ai_execution")

    worker_ner.executar_worker_ner()

    # Não deve gastar IO tentando salvar nada
    mock_get_or_create.assert_not_called()
    mock_link.assert_not_called()

    # MAS DEVE CARIMBAR O LOG, senão o documento ficaria preso na fila para sempre!
    mock_carimbar.assert_called_once_with(mock_db, "gold-vazio", "ner_spacy")
    mock_db.commit.assert_called_once()

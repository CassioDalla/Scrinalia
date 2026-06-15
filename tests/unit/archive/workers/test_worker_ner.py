from unittest.mock import Mock

from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive import repository
from domains.archive.workers import worker_ner


# ==========================================
# 1. TESTES UNITÁRIOS DE LÓGICA PURA (NLP)
# ==========================================

def test_extract_entities_text_sucesso(mocker: MockerFixture) -> None:
    """Testa se entidades legítimas são capturadas, limpas e padronizadas com Title Case."""
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
    assert resultado[0].name == "David Carneiro"
    assert resultado[0].entity_type == "PER"
    assert resultado[1].name == "Rua Brigadeiro Franco"
    assert resultado[1].entity_type == "LOC"


def test_extract_entities_text_data_quality_filtra_lixo(mocker: MockerFixture) -> None:
    """Garante que a esteira descarte ruídos textuais (strings muito curtas ou excessivamente longas)."""
    mock_ent_curta = mocker.Mock()
    mock_ent_curta.text = "X"
    mock_ent_curta.label_ = "LOC"
    mock_ent_curta.ent_id_ = ""

    mock_ent_longa = mocker.Mock()
    mock_ent_longa.text = "A" * 155
    mock_ent_longa.label_ = "ORG"
    mock_ent_longa.ent_id_ = ""

    mock_doc = mocker.Mock()
    mock_doc.ents = [mock_ent_curta, mock_ent_longa]

    mock_nlp_engine = mocker.Mock(return_value=mock_doc)

    resultado = worker_ner.extract_entities_text("Texto...", mock_nlp_engine)

    assert len(resultado) == 0


# ==========================================
# 2. TESTES DE INTEGRALIDADE DO WORKER (ORQUESTRADOR)
# ==========================================

def test_execute_worker_ner_fluxo_completo(mocker: MockerFixture) -> None:
    """Testa o caminho feliz: lê documento pendente, extrai entidades, salva e carimba checkpoint."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_ner, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    
    # CORREÇÃO: Usando MagicMock para suportar o db.begin_nested()
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Previne o spaCy de ser carregado de verdade durante os testes
    mocker.patch("spacy.load", return_value=mocker.Mock())
    mocker.patch.object(repository, "get_ner_synonyms_rules", return_value=[])

    doc_archive_fake = Mock()
    doc_archive_fake.description_id = "archive-dossie-1"
    doc_archive_fake.original_title = "Título Legal"
    doc_archive_fake.admin_bio_history = "Histórico do produtor David Carneiro."
    doc_archive_fake.provenance = "Coleção Particular."
    doc_archive_fake.scope_content = "Conteúdo rico de Curitiba."

    mock_query = Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_archive_fake]

    fake_dto = Mock()
    mocker.patch.object(worker_ner, "extract_entities_text", return_value=[fake_dto])

    mock_get_or_create = mocker.patch.object(repository, "get_or_create_entities", return_value=[777])
    mock_link = mocker.patch.object(repository, "link_description_relationships")
    mock_carimbar = mocker.patch.object(repository, "stamp_ai_execution")

    worker_ner.execute_worker_ner()

    mock_get_or_create.assert_called_once_with(mock_db, [fake_dto])
    mock_link.assert_called_once_with(mock_db, description_id="archive-dossie-1", entity_ids=[777], tag_ids=[])
    # Garante que o passaporte foi carimbado com a chave atualizada
    mock_carimbar.assert_called_once_with(mock_db, "archive-dossie-1", "ner_spacy_v1")
    mock_db.commit.assert_called_once()


def test_execute_worker_ner_vazio_obrigatoriamente_carimba_log(mocker: MockerFixture) -> None:
    """Garante que se o documento não possuir entidades, o checkpoint é gravado mesmo assim."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_ner, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    
    # CORREÇÃO: Usando MagicMock para suportar o db.begin_nested()
    mock_db.begin_nested.return_value = mocker.MagicMock()

    mocker.patch("spacy.load", return_value=mocker.Mock())
    mocker.patch.object(repository, "get_ner_synonyms_rules", return_value=[])

    doc_archive_fake = Mock()
    doc_archive_fake.description_id = "archive-vazio"
    doc_archive_fake.original_title = None
    doc_archive_fake.admin_bio_history = None
    doc_archive_fake.provenance = None
    doc_archive_fake.scope_content = None

    mock_query = Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_archive_fake]

    mocker.patch.object(worker_ner, "extract_entities_text", return_value=[])

    mock_get_or_create = mocker.patch.object(repository, "get_or_create_entities")
    mock_link = mocker.patch.object(repository, "link_description_relationships")
    mock_carimbar = mocker.patch.object(repository, "stamp_ai_execution")

    worker_ner.execute_worker_ner()

    mock_get_or_create.assert_not_called()
    mock_link.assert_not_called()
    mock_carimbar.assert_called_once_with(mock_db, "archive-vazio", "ner_spacy_v1")
    mock_db.commit.assert_called_once()
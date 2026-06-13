from unittest.mock import Mock

from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from core.crud import gold_crud
from core.schemas.gold_schema import GoldDescriptionDTO
from scripts.gold import worker_load_gold

# ==========================================
# 1. TESTES DE LÓGICA DE NEGÓCIO (Limpeza de Tags)
# ==========================================


def test_extract_tags_sucess() -> None:
    """Testa a limpeza de stopwords de domínio e a normalização de múltiplas tags."""
    texto_bruto = "Ofício, Curitiba, Indústria Têxtil, Fábrica de Cortinas e Toalhas, Colombo"

    stopword_list = {"ofício", "curitiba"}
    resultado = worker_load_gold.extract_tags(texto_bruto, stopword_list)

    # Extrai apenas os nomes para facilitar a validação
    nomes_tags = {dto.name for dto in resultado}

    # 'ofício' e 'curitiba' são stopwords, então devem ter sumido
    assert len(resultado) == 3
    assert "indústria têxtil" in nomes_tags
    assert "fábrica de cortinas e toalhas" in nomes_tags
    assert "colombo" in nomes_tags

    # O DTO deve vir com a macro_category vazia para o mDeBERTa preencher
    assert resultado[0].macro_category is None


def test_extract_tags_data_quality() -> None:
    """Testa se a função barra tags excessivamente longas ou curtas (lixo)."""
    # 'A' = 1 letra (inválida)
    # Lixo legível = > 100 caracteres (inválida)
    texto_bruto = "A, Curitiba, " + ("X" * 105) + ", Manutenção"

    stopword_list = {"curitiba"}
    resultado = worker_load_gold.extract_tags(texto_bruto, stopword_list)

    assert len(resultado) == 1
    assert resultado[0].name == "manutenção"


def test_extract_tags_null() -> None:
    """Garante que a esteira não quebra se o documento original não tiver tags."""
    resultado = worker_load_gold.extract_tags(None, set())
    assert resultado == []


# ==========================================
# 2. TESTES DE ORQUESTRAÇÃO E TRANSAÇÃO (Worker Principal)
# ==========================================


def test_executar_migracao_fluxo_completo(mocker: MockerFixture) -> None:
    """Testa o caminho feliz, onde um documento inédito é inserido na Gold."""
    mock_db = mocker.Mock(spec=Session)

    # 1. Intercepta a abertura de sessão do banco
    mock_get_db = mocker.patch.object(worker_load_gold, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mocker.patch.object(gold_crud, "get_stopwords", return_value={"tag teste"})

    doc_silver = Mock()
    doc_silver.description_id = "doc-100"
    doc_silver.title = "Dossiê Teste"
    doc_silver.document_date = None
    doc_silver.scope_content = "Resumo do documento"
    doc_silver.bronze_content_hash = "hash_123"
    doc_silver.reference_code = "BR PR"
    doc_silver.level = "Dossiê"
    doc_silver.producers = "Prefeitura"
    doc_silver.admin_bio_history = None
    doc_silver.admin_archival_history = None
    doc_silver.provenance = None
    doc_silver.language_name = "pt-BR"
    doc_silver.archivist_notes = None
    doc_silver.indexing_points = "Tag Teste"
    doc_silver.thumb_down_link = ""

    # Simula o yield_per do SQLAlchemy retornando nossa lista
    mock_query = Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_silver]

    # 3. Intercepta as funções pesadas do CRUD
    # Simulamos que o Upsert deu True (Dado alterado/inserido)
    mock_upsert = mocker.patch.object(gold_crud, "upsert_gold_description", return_value=True)
    # Simulamos que a tag gerou o ID 99 no banco
    mock_tags = mocker.patch.object(gold_crud, "get_or_create_tags", return_value=[99])
    mock_link = mocker.patch.object(gold_crud, "link_description_relationships")

    # 4. Executa
    worker_load_gold.executar_migracao_silver_gold()

    # 5. Validação de Comportamento
    assert mock_upsert.call_count == 1

    # Captura e valida o DTO que o Worker montou para enviar pro CRUD
    args, _ = mock_upsert.call_args
    dto_enviado: GoldDescriptionDTO = args[1]

    assert dto_enviado.description_id == "doc-100"
    assert dto_enviado.original_title == "Dossiê Teste"
    assert dto_enviado.silver_content_hash == "hash_123"
    assert dto_enviado.execution_log == {"migracao_base": "completed"}

    # Verifica o processamento em cascata e vínculos N:N
    mock_tags.assert_called_once()
    mock_link.assert_called_once_with(mock_db, description_id="doc-100", entity_ids=[], tag_ids=[99])

    # Valida se finalizou a transação
    mock_db.commit.assert_called_once()


def test_executar_migracao_idempotencia(mocker: MockerFixture) -> None:
    """Testa a Carga Incremental: Se o Hash for igual, o Upsert retorna False e o pipeline pula o documento."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_load_gold, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mocker.patch.object(gold_crud, "get_stopwords", return_value={"tag teste"})

    doc_silver = Mock()
    doc_silver.description_id = "doc-100"
    doc_silver.title = "Teste"
    doc_silver.document_date = None
    doc_silver.scope_content = "Resumo"
    doc_silver.bronze_content_hash = "hash_123"
    doc_silver.reference_code = "BR"
    doc_silver.level = "Item"
    doc_silver.producers = None
    doc_silver.admin_bio_history = None
    doc_silver.admin_archival_history = None
    doc_silver.provenance = None
    doc_silver.language_name = "pt"
    doc_silver.archivist_notes = None
    doc_silver.indexing_points = None
    doc_silver.thumb_down_link = ""

    mock_query = Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_silver]

    # Simulamos o PostgreSQL bloqueando o UPDATE por Hash igual
    mock_upsert = mocker.patch.object(gold_crud, "upsert_gold_description", return_value=False)
    mock_tags = mocker.patch.object(gold_crud, "get_or_create_tags")
    mock_link = mocker.patch.object(gold_crud, "link_description_relationships")

    worker_load_gold.executar_migracao_silver_gold()

    mock_upsert.assert_called_once()
    # Se o documento já existia, NÃO devemos recriar tags ou vínculos
    mock_tags.assert_not_called()
    mock_link.assert_not_called()

    mock_db.commit.assert_called_once()


def test_executar_migracao_rollback_no_erro(mocker: MockerFixture) -> None:
    """Garante a blindagem do banco em caso de erro no meio do lote."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_load_gold, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db

    doc_silver = Mock()
    mock_query = Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_silver]

    # Força uma exceção crítica ao tentar inserir o dado
    mocker.patch.object(gold_crud, "upsert_gold_description", side_effect=ValueError("PostgreSQL fora do ar"))

    worker_load_gold.executar_migracao_silver_gold()

    # O script DEVE chamar o rollback imediatamente para evitar DB locks
    mock_db.rollback.assert_called_once()

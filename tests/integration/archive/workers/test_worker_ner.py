from unittest.mock import patch

from sqlalchemy import select

from domains.archive.models import ArchiveDocument, ArchiveDocumentEntity, ArchiveEntity
from domains.archive.schemas.entity_schema import ArchiveEntityDTO
from domains.archive.workers.worker_ner import execute


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integracao_banco_real(
    mock_get_engine,
    db_session,  # A sua sessão PostgreSQL injetada!
    generate_archive_doc,  # A sua fábrica de documentos
):
    """Integração: Testa o SQL real de inserção de Entidades e a manipulação do campo JSONB."""
    mock_ner_engine = mock_get_engine.return_value

    # 1. MOCK DA IA: Simulamos a IA a encontrar 2 entidades no texto
    mock_ner_engine.extract.return_value = [
        [
            ArchiveEntityDTO(name="David Carneiro", entity_type="PER"),
            ArchiveEntityDTO(name="Curitiba", entity_type="LOC"),
        ]
    ]

    # 2. SETUP: Inserimos um documento real no PostgreSQL
    doc_real = generate_archive_doc(
        description_id="doc_ner_1",
        original_title="Relatório Anual",
        scope_content="Documento emitido na cidade de Curitiba por David Carneiro.",
    )
    db_session.add(doc_real)
    db_session.commit()

    # 3. AÇÃO: O Worker roda usando a sessão real (Não mockamos o repositório!)
    execute(db=db_session)

    # 4. VERIFICAÇÕES: Documento atualizado
    db_session.expire_all()  # Limpa o cache para forçar a leitura fresca do banco
    doc_atualizado = db_session.get(ArchiveDocument, "doc_ner_1")

    # Verifica se o JSONB foi gravado perfeitamente no disco
    assert doc_atualizado.execution_log is not None
    assert doc_atualizado.execution_log["worker_ner_v1"] == "DONE"

    # Confirma o envio correto do texto concatenado para a IA
    args, _ = mock_ner_engine.extract.call_args
    assert args[0] == ["Relatório Anual. Documento emitido na cidade de Curitiba por David Carneiro."]

    # 5. VERIFICAÇÕES: O banco de dados recebeu os inserts corretos?
    entidades_banco = db_session.scalars(select(ArchiveEntity)).all()
    assert len(entidades_banco) == 2
    nomes = {e.name for e in entidades_banco}

    assert "David Carneiro" in nomes
    assert "Curitiba" in nomes

    # Verifica se a tabela associativa (N:N) foi preenchida
    vinculos = db_session.scalars(select(ArchiveDocumentEntity)).all()
    assert len(vinculos) == 2


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integracao_ignora_documentos_ja_processados(mock_get_engine, db_session, generate_archive_doc):
    """Integração: Valida se a query WHERE do SQLAlchemy respeita a negação do JSONB no PostgreSQL."""
    # Inserimos um documento no banco real que JÁ POSSUI o carimbo
    doc_velho = generate_archive_doc(
        original_title="Documento Antigo", execution_log={"worker_ner_v1": "DONE", "algum_outro_worker": "ERROR"}
    )
    db_session.add(doc_velho)
    db_session.commit()

    # Executa o orquestrador
    execute(db=db_session)

    # Verifica se a IA foi completamente ignorada, pois a query do banco deve ter retornado vazia
    mock_get_engine.return_value.extract.assert_not_called()


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integracao_processa_multiplos_lotes(mock_get_engine, db_session, generate_archive_doc):
    """Integração: Valida se o 'while True' avança corretamente pelas páginas de limite (limit) no DB."""
    mock_ner_engine = mock_get_engine.return_value

    # Criamos 3 documentos no banco
    docs = [
        generate_archive_doc(description_id="doc-1", original_title="Texto 1"),
        generate_archive_doc(description_id="doc-2", original_title="Texto 2"),
        generate_archive_doc(description_id="doc-3", original_title="Texto 3"),
    ]
    db_session.add_all(docs)
    db_session.commit()

    # O Mock da IA precisa retornar listas de entidades vazias condizentes com os lotes.
    # Lote 1 tem 2 documentos (retorna [[], []]). Lote 2 tem 1 documento (retorna [[]]).
    mock_ner_engine.extract.side_effect = [[[], []], [[]]]

    # Executamos forçando um batch_size minúsculo de 2
    # Isso forçará o worker a dar 2 voltas no laço while
    execute(db=db_session, db_batch_size=2)

    db_session.expire_all()

    # Todos os 3 documentos precisam ter o carimbo DONE salvo no banco
    assert db_session.get(ArchiveDocument, "doc-1").execution_log["worker_ner_v1"] == "DONE"
    assert db_session.get(ArchiveDocument, "doc-2").execution_log["worker_ner_v1"] == "DONE"
    assert db_session.get(ArchiveDocument, "doc-3").execution_log["worker_ner_v1"] == "DONE"

    # A inferência da IA (o extract em lote) deve ter sido chamada exatamente 2 vezes
    assert mock_ner_engine.extract.call_count == 2


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integracao_ignora_linhas_100_nulas(mock_get_engine, db_session, generate_archive_doc):
    """Integração: Valida a montagem do or_() dinâmico no SQLAlchemy. Docs sem textos não entram na fila."""
    # Documento onde os campos que pedimos para extrair estão explicitamente None
    doc_fantasma = generate_archive_doc(
        description_id="doc_fantasma",
        original_title="Titulo teste doc",
        admin_bio_history=None,
        provenance=None,
        scope_content=None,
    )
    db_session.add(doc_fantasma)
    db_session.commit()

    # Rodamos o worker pedindo para ele olhar APENAS para os campos que sabemos que estão None
    execute(db=db_session, columns_to_extract=["scope_content", "admin_bio_history"])

    # A query do banco deve ignorar essa linha sumariamente no or_(*filters)
    mock_get_engine.return_value.extract.assert_not_called()

    # O documento no banco deve continuar intocado (sem execution_log criado)
    db_session.expire_all()
    doc_verificado = db_session.get(ArchiveDocument, "doc_fantasma")
    assert doc_verificado.execution_log is None or "worker_ner_v1" not in doc_verificado.execution_log

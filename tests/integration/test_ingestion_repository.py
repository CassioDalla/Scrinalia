from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from domains.ingestion.models import ScrapeStatus, ScrapingQueue
from domains.ingestion.repository import add, add_in_bulk, get_from_queue, update_queue_status

# ==========================================
# 1. TESTES DE INSERÇÃO SIMPLES (ADD)
# ==========================================


def test_add_success(use_test_db, db_session):
    """Garante que um documento inédito é inserido corretamente na fila."""
    item = add(db_session, "doc_123")

    assert item is not None
    assert item.description_id == "doc_123"
    assert item.scrape_status == ScrapeStatus.PENDING
    assert item.retry_count == 0


def test_add_duplicate_integrity_error(use_test_db, db_session):
    """Testa a proteção do banco. Se o ID já existir, deve dar rollback suave e retornar None."""
    # Inserção original
    add(db_session, "doc_duplicado")

    # Tentativa de duplicata
    item_repetido = add(db_session, "doc_duplicado")

    assert item_repetido is None
    # Garante que o banco continua operante após o rollback
    qtd = db_session.query(ScrapingQueue).count()
    assert qtd == 1


# ==========================================
# 2. TESTES DE INSERÇÃO EM LOTE (BULK INSERT)
# ==========================================


def test_add_in_bulk_success(use_test_db, db_session):
    """Testa a inserção rápida de múltiplos IDs simultâneos."""
    ids = ["doc_1", "doc_2", "doc_3"]
    qtd_inserida = add_in_bulk(db_session, ids)

    assert qtd_inserida == 3
    qtd_banco = db_session.query(ScrapingQueue).count()
    assert qtd_banco == 3


def test_add_in_bulk_ignore_duplicates(use_test_db, db_session):
    """Testa o ON CONFLICT DO NOTHING. IDs repetidos devem ser ignorados silenciosamente."""
    # Primeiro lote
    add_in_bulk(db_session, ["doc_A", "doc_B"])

    # Segundo lote (doc_B já existe, doc_C é novo)
    qtd_novos = add_in_bulk(db_session, ["doc_B", "doc_C"])

    # Apenas o doc_C deve ser contabilizado como inserção nova
    assert qtd_novos == 1
    qtd_total = db_session.query(ScrapingQueue).count()
    assert qtd_total == 3


def test_add_in_bulk_empty_list(use_test_db, db_session):
    """Garante que enviar uma lista vazia não quebra o SQL."""
    qtd = add_in_bulk(db_session, [])
    assert qtd == 0


# ==========================================
# 3. TESTES DE RECUPERAÇÃO (SLIDING WINDOW)
# ==========================================


def test_get_from_queue_nulls_first(use_test_db, db_session):
    """Garante que documentos que NUNCA foram raspados (Null) venham antes na fila."""
    hoje = datetime.now(UTC)

    doc_velho = ScrapingQueue(description_id="doc_velho", last_scraped_at=hoje - timedelta(days=5))
    doc_novo = ScrapingQueue(description_id="doc_novo", last_scraped_at=hoje)
    doc_virgem = ScrapingQueue(description_id="doc_virgem", last_scraped_at=None)  # Nunca raspado

    db_session.add_all([doc_velho, doc_novo, doc_virgem])
    db_session.commit()

    fila = get_from_queue(db_session)

    assert len(fila) == 3
    # A ordenação deve ser: NULLS FIRST, depois do mais antigo para o mais recente
    assert fila[0].description_id == "doc_virgem"
    assert fila[1].description_id == "doc_velho"
    assert fila[2].description_id == "doc_novo"


def test_get_from_queue_ignore_status(use_test_db, db_session):
    """Garante que os status ignorados não poluem a busca da fila."""
    doc_pendente = ScrapingQueue(description_id="doc_p", scrape_status=ScrapeStatus.PENDING)
    doc_fatal = ScrapingQueue(description_id="doc_f", scrape_status=ScrapeStatus.FATAL_ERROR)

    db_session.add_all([doc_pendente, doc_fatal])
    db_session.commit()

    fila = get_from_queue(db_session, ignore_status=[ScrapeStatus.FATAL_ERROR])

    assert len(fila) == 1
    assert fila[0].description_id == "doc_p"


def test_get_from_queue_sliding_window(use_test_db, db_session):
    """Testa os filtros de janela de tempo (scraped_before)."""
    agora = datetime.now(UTC)
    ontem = agora - timedelta(days=1)
    semana_passada = agora - timedelta(days=7)

    doc_recente = ScrapingQueue(description_id="doc_recente", last_scraped_at=ontem)
    doc_expirado = ScrapingQueue(description_id="doc_expirado", last_scraped_at=semana_passada)

    db_session.add_all([doc_recente, doc_expirado])
    db_session.commit()

    # Pede documentos que foram raspados ANTES de 3 dias atrás
    limite = agora - timedelta(days=3)
    fila = get_from_queue(db_session, scraped_before=limite)

    assert len(fila) == 1
    assert fila[0].description_id == "doc_expirado"


# ==========================================
# 4. TESTES DE ATUALIZAÇÃO DE STATUS (UPDATE)
# ==========================================


def test_update_queue_status_success(use_test_db, db_session):
    """Garante que um sucesso (DONE) zera as retentativas e marca a hora exata."""
    # Cria doc com erros passados
    doc = ScrapingQueue(description_id="doc_1", retry_count=2, scrape_status=ScrapeStatus.PENDING)
    db_session.add(doc)
    db_session.commit()

    resultado = update_queue_status(db_session, "doc_1", ScrapeStatus.DONE)
    assert resultado is True

    db_session.expire_all()
    doc_atualizado = db_session.execute(select(ScrapingQueue).filter_by(description_id="doc_1")).scalar_one()

    assert doc_atualizado.scrape_status == ScrapeStatus.DONE
    assert doc_atualizado.retry_count == 0  # Zerado!
    assert doc_atualizado.last_scraped_at is not None


def test_update_queue_status_increment_retry(use_test_db, db_session):
    """Testa erro transitório: deve somar +1 na contagem e salvar o log de erro."""
    doc = ScrapingQueue(description_id="doc_2", retry_count=1)
    db_session.add(doc)
    db_session.commit()

    update_queue_status(db_session, "doc_2", ScrapeStatus.NETWORK_ERROR, error_msg="Timeout 504", increment_retry=True)

    db_session.expire_all()
    doc_atualizado = db_session.execute(select(ScrapingQueue).filter_by(description_id="doc_2")).scalar_one()

    assert doc_atualizado.retry_count == 2  # Incrementou 1 + 1
    assert doc_atualizado.scrape_status == ScrapeStatus.NETWORK_ERROR
    assert doc_atualizado.last_error_message == "Timeout 504"


def test_update_queue_status_fatal_error(use_test_db, db_session):
    """Testa erro definitivo: altera o status e erro, mas NÃO altera a contagem de retry."""
    doc = ScrapingQueue(description_id="doc_3", retry_count=3)
    db_session.add(doc)
    db_session.commit()

    update_queue_status(db_session, "doc_3", ScrapeStatus.FATAL_ERROR, error_msg="404 Not Found", increment_retry=False)

    db_session.expire_all()
    doc_atualizado = db_session.execute(select(ScrapingQueue).filter_by(description_id="doc_3")).scalar_one()

    assert doc_atualizado.retry_count == 3  # Continua intacto
    assert doc_atualizado.scrape_status == ScrapeStatus.FATAL_ERROR
    assert doc_atualizado.last_error_message == "404 Not Found"


def test_update_queue_status_not_found(use_test_db, db_session):
    """Garante que tentar atualizar um ID que não existe retorna False de forma segura."""
    resultado = update_queue_status(db_session, "id_fantasma", ScrapeStatus.DONE)
    assert resultado is False

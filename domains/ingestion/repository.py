import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.logger import logger

from .models import RawData, ScrapeStatus, ScrapingQueue


def add(db: Session, description_id: str) -> ScrapingQueue | None:
    """
    Adiciona um novo ID de documento à fila de ingestão.

    Tenta inserir um novo identificador na base. Se o ID já existir
    (violação de UNIQUE constraint), a transação é desfeita e a duplicidade
    é ignorada silenciosamente.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        description_id (str): Identificador único do documento na fonte externa.

    Returns:
        ScrapingQueue | None: A instância do objeto inserido, ou None caso
        o ID já exista ou ocorra uma falha de banco de dados.
    """

    item = ScrapingQueue(description_id=description_id)
    try:
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    except IntegrityError:
        db.rollback()
        logger.debug(f"Descrição de ID: {description_id} ja existe no banco. Ignorado")
        return None

    except Exception as e:
        logger.critical(f"Erro crítico de banco de dados ao inserir o description_id {description_id}: {e}")
        db.rollback()
        return None


def add_in_bulk(db: Session, description_id_list: list[str]) -> int:
    """
    Insere uma lista de IDs na fila de processamento em lote (Bulk Insert).

    Utiliza a instrução 'ON CONFLICT DO NOTHING' nativa do PostgreSQL para garantir
    alta performance de I/O, ignorando as linhas de IDs que já estiverem cadastradas
    sem abortar a transação.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        description_id_list (list[str]): Lista contendo os IDs recém-descobertos.

    Returns:
        int: A quantidade exata de registros inéditos que foram inseridos no banco.
    """

    if not description_id_list:
        return 0

    data = [{"description_id": desc_id} for desc_id in description_id_list]

    try:
        stmt = insert(ScrapingQueue).values(data)
        stmt = stmt.on_conflict_do_nothing(index_elements=["description_id"])
        stmt = stmt.returning(ScrapingQueue.description_id)
        inserted_ids = db.scalars(stmt).all()
        db.commit()

        return len(inserted_ids)

    except Exception as e:
        db.rollback()
        logger.exception(f"💥 Falha no bulk insert de {len(description_id_list)} IDs: {e}")
        return 0


def get_from_queue(
    db: Session,
    ignore_status: list[ScrapeStatus] | None = None,
    discovered_after: datetime | None = None,
    scraped_before: datetime | None = None,
) -> Sequence[ScrapingQueue]:
    """
    Busca um lote de documentos na fila pendentes de extração de detalhes.

    Aplica as regras de negócio de 'Sliding Window', retornando IDs que
    nunca foram processados (NULLS FIRST) ou que já ultrapassaram o tempo
    de vida útil (TTL) e precisam ser checados novamente para atualização.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        ignore_status (list[ScrapeStatus] | None): Lista de status que não devem ser retornados.
        discovered_after (datetime | None): Filtro de janela temporal de descoberta.
        scraped_before (datetime | None): Filtro de janela temporal de obsolescência (TTL).

    Returns:
        Sequence[ScrapingQueue]: Lista de entidades da fila prontas para o Adapter.
    """
    stmt = select(ScrapingQueue)

    if discovered_after is not None:
        stmt = stmt.where(ScrapingQueue.discovered_at >= discovered_after)

    if scraped_before is not None:
        stmt = stmt.where(
            or_(
                ScrapingQueue.last_scraped_at.is_(None),  # Nunca foi raspado
                ScrapingQueue.last_scraped_at <= scraped_before,  # Ou a janela de tempo já venceu
            )
        )

    if ignore_status:
        stmt = stmt.where(ScrapingQueue.scrape_status.notin_(ignore_status))

    stmt = stmt.order_by(ScrapingQueue.last_scraped_at.asc().nulls_first())

    return db.scalars(stmt).all()


def update_queue_status(
    db: Session,
    description_id: str,
    status: ScrapeStatus,
    error_msg: str | None = None,
    increment_retry: bool = False,
) -> bool:
    """
    Atualiza o estado de um documento na fila após uma tentativa de ingestão.

    Realiza um comando de UPDATE atômico direto no banco de dados, registrando
    o momento exato da operação. Gerencia a contagem de falhas transitórias (retries)
    e a captura de logs de erro repassados pelos Adapters.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        description_id (str): Identificador único do documento.
        status (ScrapeStatus): Novo status a ser aplicado (ex: DONE, FATAL_ERROR).
        error_msg (str | None): Mensagem de erro originada no domínio ou adaptador.
        increment_retry (bool): Se True, soma +1 ao contador de falhas do ID.

    Returns:
        bool: True se a fila foi atualizada com sucesso, False se o ID não existir.
    """

    now = datetime.now(UTC)

    stmt = update(ScrapingQueue).where(ScrapingQueue.description_id == description_id)

    if status == ScrapeStatus.DONE:
        # Sucesso: Zera o contador de retentativas
        stmt = stmt.values(scrape_status=status, last_scraped_at=now, retry_count=0)
    elif increment_retry:
        # Falha transitória: Incrementa +1
        stmt = stmt.values(
            scrape_status=status,
            last_scraped_at=now,
            retry_count=ScrapingQueue.retry_count + 1,
            last_error_message=error_msg,
        )
    else:
        # Falha fatal: Apenas muda o status, não mexe no contador
        stmt = stmt.values(scrape_status=status, last_scraped_at=now, last_error_message=error_msg)

    stmt = stmt.returning(ScrapingQueue.description_id)

    try:
        # Se db.scalar() retornar o ID, a linha foi encontrada e atualizada
        updated_id = db.scalar(stmt)
        db.commit()

        if updated_id is None:
            logger.warning(f"Tentativa de atualizar status de ID inexistente: {description_id}")
            return False

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Erro no banco ao atualizar status da fila para {description_id}: {e}")
        return False


def save_raw_data(db: Session, description_id: str, scraped_data: dict) -> bool:
    """
    Persiste os dados brutos extraídos pelo Adapter na camada de Ingestão.

    Calcula um hash SHA-256 do payload recebido para controle de idempotência.
    Utiliza 'UPSERT' (ON CONFLICT DO UPDATE) do PostgreSQL com uma condicional
    para ignorar a atualização física no disco caso o hash do conteúdo capturado
    seja idêntico ao já existente no banco.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        description_id (str): Identificador único do documento na fonte externa.
        scraped_data (dict): Dicionário bruto contendo os metadados extraídos.

    Raises:
        Exception: Repassa qualquer erro crítico de banco para o Orquestrador tratar.

    Returns:
        bool: True se os dados foram inseridos ou checados com sucesso.
    """
    raw_title = scraped_data.get("title")

    string_payload = json.dumps(scraped_data, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(string_payload.encode("utf-8")).hexdigest()

    values = {
        "description_id": description_id,
        "raw_title": raw_title,
        "payload": scraped_data,
        "content_hash": content_hash,
    }

    try:
        stmt = insert(RawData).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["description_id"],
            set_={
                "raw_title": stmt.excluded.raw_title,
                "payload": stmt.excluded.payload,
                "content_hash": stmt.excluded.content_hash,
                "updated_at": func.now(),
            },
            where=(RawData.content_hash != stmt.excluded.content_hash),
        )
        db.execute(stmt)
        db.commit()
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Falha grave no banco ao salvar {description_id} na ingestão: {e}")
        raise e

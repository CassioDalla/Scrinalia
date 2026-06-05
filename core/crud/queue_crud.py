from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.logger import logger
from core.models import ScrapeStatus, ScrapingQueue


def add(db: Session, description_id: str) -> ScrapingQueue | None:
    """
    Adiciona um novo ID de descrição à fila de processamento.

    Tenta inserir um novo documento na base. Se o documento já existir
    (violação de UNIQUE constraint), a transação é desfeita de forma segura e
    ignorada.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        description_id (str): O ID legado da descrição no sistema ArqDoc.

    Returns:
        ScrapingQueue | None: A instância do objeto inserido no banco, ou None
        caso o ID já exista ou ocorra uma falha crítica.
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

    Utiliza a instrução 'ON CONFLICT DO NOTHING' do PostgreSQL para garantir
    alta performance, ignorando silenciosamente os IDs que já estiverem cadastrados.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        description_id_list (list[str]): Lista contendo os IDs extraídos do ArqDoc.

    Returns:
        int: A quantidade exata de novos registros que foram de fato
        inseridos no banco de dados.
    """

    if not description_id_list:
        return 0

    data = [{"description_id": desc_id} for desc_id in description_id_list]

    try:
        stmt = pg_insert(ScrapingQueue).values(data)
        stmt = stmt.on_conflict_do_nothing(index_elements=["description_id"])
        stmt = stmt.returning(ScrapingQueue.description_id)
        inserted_ids = db.scalars(stmt).all()
        db.commit()

        return len(inserted_ids)

    except Exception as e:
        db.rollback()
        logger.exception(f"💥 Falha no bulk insert de {len(description_id_list)} IDs: {e}")
        return 0


def get_ids_to_scrape_details(
    db: Session,
    ignore_status: list[ScrapeStatus] | None = None,
    discovered_after: datetime | None = None,
    scraped_before: datetime | None = None,
) -> Sequence[ScrapingQueue]:
    """
    Busca documentos na fila que precisam ter seus detalhes extraidos.

    Aplica a lógica de Sliding Window retornando documentos
    que nunca foram extraidos ou que estão dentro da janela de tempo e precisam
    de atualização, ignorando os que possuam status passados no argumento.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        discovered_after (datetime | None) Data limite inferior da descoberta do documento (Timezone-Aware).
        scraped_before (datetime | None): Data limite superior de quando o documento foi extraido pela última vez (Timezone-Aware).
        ignore_status (list[ScrapeStatus]): Lista de status do ENUM que devem ser excluídos da busca.

    Returns:
        Sequence[ScrapingQueue]: Uma lista de objetos da fila prontos para processamento.
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
    Atualiza o status de um documento na fila de extração de forma performática.

    Utiliza um comando UPDATE direto no banco de dados (evitando um SELECT prévio),
    e sempre atualiza a data de 'last_scraped_at' para o momento atual.

    Args:
        db (Session): Sessão ativa do banco de dados.
        description_id (str): ID legado do documento.
        status (ScrapeStatus): Novo status a ser aplicado.
        error_msg (str | None, opcional): Mensagem de erro capturada pela exceção.
        increment_retry (bool): Incrementa retry count

    Returns:
        bool: True se a linha foi atualizada com sucesso, False caso o ID não exista ou ocorra erro.
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
            last_error_messag=error_msg,
        )
    else:
        # Falha fatal: Apenas muda o status, não mexe no contador
        stmt = stmt.values(scrape_status=status, last_scraped_at=now, last_error_messag=error_msg)

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

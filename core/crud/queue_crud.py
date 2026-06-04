from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.logger import logger
from core.models import ScrapingQueue


def add(db: Session, description_id: str):
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


def add_in_bulk(db: Session, description_id_list: list[str]):
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

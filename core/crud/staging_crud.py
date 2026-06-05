import hashlib
import json

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.logger import logger
from core.models.staging import StagingDescription


def save_scraped_description(db: Session, description_id: str, scraped_data: dict) -> bool:

    raw_title = scraped_data.get("title")

    string_payload = json.dumps(scraped_data, sort_keys=True)
    content_hash = hashlib.sha256(string_payload.encode("utf-8")).hexdigest()

    values = {
        "description_id": description_id,
        "raw_title": raw_title,
        "payload": scraped_data,
        "content_hash": content_hash,
    }

    try:
        stmt = insert(StagingDescription).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["description_id"],
            set_={
                "raw_title": stmt.excluded.raw_title,
                "payload": stmt.excluded.payload,
                "content_hash": stmt.excluded.content_hash,
                "updated_at": func.now(),
            },
            where=(StagingDescription.content_hash != stmt.excluded.content_hash),
        )
        db.execute(stmt)
        db.commit()
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Falha grave no banco ao salvar a Staging de {description_id}: {e}")
        raise e

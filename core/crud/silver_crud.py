from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.models.silver_layer import SilverDescriptionModel
from core.schemas.silver_schema import SilverDescription


def get_pending_bronze_records(db: Session) -> list[dict[str, Any]]:
    """
    Executa a query de Rastreamento de Hash.
    Retorna apenas documentos novos ou que foram alterados na prefeitura.
    """
    query = text("""
        SELECT
            b.description_id,
            b.payload,
            b.content_hash,
            b.raw_title
        FROM staging_descriptions b
        LEFT JOIN silver_descriptions s ON b.description_id = s.description_id
        WHERE s.description_id IS NULL
           OR s.bronze_content_hash != b.content_hash;
    """)

    result = db.execute(query)
    return [dict(row._mapping) for row in result]


def upsert_silver_record(db: Session, record: SilverDescription) -> None:
    """
    Insere o dado limpo na Camada Silver. Se o description_id já existir
    (porque o hash mudou e estamos reprocessando), ele atualiza todas as colunas.
    """
    # Converte o modelo Pydantic validado para um dicionário nativo
    silver_dict = record.model_dump(exclude_unset=True)

    stmt = insert(SilverDescriptionModel).values(silver_dict)
    stmt = stmt.on_conflict_do_update(index_elements=["description_id"], set_=silver_dict)

    db.execute(stmt)

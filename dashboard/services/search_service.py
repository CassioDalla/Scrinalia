from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.models.gold_layer import GoldDescriptionModel


def search_document(termo_busca: str, limite: int = 50):
    """Encapsula toda a lógica de acesso a dados da Camada Ouro."""
    with get_db() as db:
        query = select(GoldDescriptionModel).options(
            selectinload(GoldDescriptionModel.tags), selectinload(GoldDescriptionModel.entities)
        )

        if termo_busca:
            busca_like = f"%{termo_busca}%"
            query = query.where(
                GoldDescriptionModel.original_title.ilike(busca_like)
                | GoldDescriptionModel.scope_content.ilike(busca_like)
            )

        query = query.limit(limite)
        return db.scalars(query).all()

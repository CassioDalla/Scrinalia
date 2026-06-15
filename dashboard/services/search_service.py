from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import get_db
from domains.archive.models import ArchiveDocument


def search_document(termo_busca: str, limite: int = 50):
    """Encapsula toda a lógica de acesso a dados da Camada Ouro."""
    with get_db() as db:
        query = select(ArchiveDocument).options(
            selectinload(ArchiveDocument.tags), selectinload(ArchiveDocument.entities)
        )

        if termo_busca:
            busca_like = f"%{termo_busca}%"
            query = query.where(
                ArchiveDocument.original_title.ilike(busca_like)
                | ArchiveDocument.scope_content.ilike(busca_like)
            )

        query = query.limit(limite)
        return db.scalars(query).all()

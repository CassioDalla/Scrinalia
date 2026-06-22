from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.archive.models import (
    ArchiveTypology,
)


def get_active_typologies(db: Session) -> dict[str, int]:
    """
    Recupera todas as tipologias de documentos cadastradas no banco de dados.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.

    Returns:
        dict[str, int]: Dicionário contendo nome+contexto e id ex {"Fotografia": 1}.
    """

    stmt = select(ArchiveTypology.typology_id, ArchiveTypology.name, ArchiveTypology.context_description)

    results = db.execute(stmt).all()

    typologies_map = {}
    for typo_id, name, description in results:
        # Cria uma label  descritiva para a IA
        # Ex: "Planta Arquitetônica: Projetos de aumento, construção e reformas."
        context_label = f"{name}: {description}" if description else name

        typologies_map[context_label] = typo_id

    return typologies_map
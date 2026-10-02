from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.models import (
    ArchiveTypology,
)


class TypologyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_typologies(self) -> dict[str, int]:
        """
        Retrieves all document typologies registered in the database.

        Args:
            db (Session): Active SQLAlchemy session.

        Returns:
            dict[str, int]: Dictionary containing name+context and id e.g. {"Fotografia": 1}.
        """

        stmt = select(ArchiveTypology.typology_id, ArchiveTypology.name, ArchiveTypology.context_description)

        results = self.db.execute(stmt).all()

        typologies_map = {}
        for typology_id, name, description in results:
            # Creates a descriptive label for the AI
            # E.g.: "Architectural Plan: Expansion, construction and renovation projects."
            context_label = f"{name}: {description}" if description else name

            typologies_map[context_label] = typology_id

        return typologies_map

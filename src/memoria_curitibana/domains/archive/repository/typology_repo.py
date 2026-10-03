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

        Only the bare name is used as the candidate label. Concatenating the context
        (``"Name: description"``) makes the model progressively lose the entailment as the
        label grows, until it collapses every document onto a single typology: measured on
        ``mDeBERTa-v3-base-mnli-xnli``, a health-related text is correctly labelled with bare
        names but flips to the first typology once the descriptions are appended, with high
        confidence on the wrong label. ``context_description`` stays in the schema as
        curator-facing documentation, deliberately kept out of the prompt.

        Args:
            db (Session): Active SQLAlchemy session.

        Returns:
            dict[str, int]: Dictionary containing name and id e.g. {"Fotografia": 1}.
        """

        stmt = select(ArchiveTypology.typology_id, ArchiveTypology.name)

        return {name: typology_id for typology_id, name in self.db.execute(stmt).all()}

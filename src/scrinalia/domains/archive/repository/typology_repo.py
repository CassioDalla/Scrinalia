from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import (
    ArchiveDocument,
    ArchiveTypology,
)
from scrinalia.domains.archive.schemas.typology_schema import (
    CreateTypologyCommand,
    UpdateTypologyCommand,
)


class TypologyRepository:
    """
    Reads and edits the documental typology catalogue.

    Like the level ladder, the catalogue has no ``delete``: ``archive_documents.typology_id`` is
    ``SET NULL``, so removing a row would unclassify every description pointing at it while
    destroying the record that the type ever existed. ``is_active`` is the way out.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_typologies(self, only_active: bool = False) -> list[ArchiveTypology]:
        stmt = select(ArchiveTypology).order_by(ArchiveTypology.name)
        if only_active:
            stmt = stmt.where(ArchiveTypology.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def get(self, typology_id: int) -> ArchiveTypology | None:
        return self.db.get(ArchiveTypology, typology_id)

    def get_by_name(self, name: str) -> ArchiveTypology | None:
        """Case-insensitive lookup: the only collision rule the catalogue has."""
        return self.db.scalars(
            select(ArchiveTypology).where(func.lower(ArchiveTypology.name) == name.strip().lower())
        ).first()

    def create(self, command: CreateTypologyCommand) -> ArchiveTypology:
        typology = ArchiveTypology(**command.model_dump())
        self.db.add(typology)
        self.db.flush()
        return typology

    def update(self, typology: ArchiveTypology, command: UpdateTypologyCommand) -> ArchiveTypology:
        for field, value in command.model_dump(exclude_unset=True).items():
            setattr(typology, field, value)
        self.db.flush()
        return typology

    def document_counts(self) -> dict[int, int]:
        """
        How many descriptions carry each typology. Derived on read, never stored.

        The retired ones are included: the count is what makes "deactivate instead of delete" a
        visible trade rather than a hidden cost.
        """
        rows = self.db.execute(
            select(ArchiveDocument.typology_id, func.count())
            .where(ArchiveDocument.typology_id.is_not(None))
            .group_by(ArchiveDocument.typology_id)
        ).all()
        return {int(typology_id): int(count) for typology_id, count in rows}

    def get_active_typologies(self) -> dict[str, int]:
        """
        The candidate labels of the zero-shot classifier: ``{typology name: typology_id}``.

        Only the bare name is used as the candidate label. Concatenating the context
        (``"Name: description"``) makes the model progressively lose the entailment as the
        label grows, until it collapses every document onto a single typology: measured on
        ``mDeBERTa-v3-base-mnli-xnli``, a health-related text is correctly labelled with bare
        names but flips to the first typology once the descriptions are appended, with high
        confidence on the wrong label. ``context_description`` stays in the schema as
        curator-facing documentation, deliberately kept out of the prompt — and out of this
        projection, so the column never even reaches the worker's payload.

        A retired typology leaves this dictionary — that is what ``is_active`` is for — while the
        descriptions already classified with it keep it.

        Returns:
            dict[str, int]: Dictionary containing name and id e.g. {"Fotografia": 1}.
        """
        stmt = (
            select(ArchiveTypology.typology_id, ArchiveTypology.name)
            .where(ArchiveTypology.is_active.is_(True))
            .order_by(ArchiveTypology.name)
        )
        return {name: typology_id for typology_id, name in self.db.execute(stmt).all()}

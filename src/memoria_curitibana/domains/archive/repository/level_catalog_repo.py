"""Persistence of the description level catalogue (Fase 2.5, H1)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.domain.hierarchy import LevelRules
from memoria_curitibana.domains.archive.domain.level_catalog import build_level_index, resolve_level_id
from memoria_curitibana.domains.archive.models import ArchiveDescriptionLevel, ArchiveDocument
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    CreateDescriptionLevelCommand,
    UpdateDescriptionLevelCommand,
)


class LevelCatalogRepository:
    """
    Reads and edits the level ladder.

    The catalogue has no ``delete``: a rung is deactivated, never removed. Deleting it would
    silently unclassify every description pointing at it (the FK is ``SET NULL``) while
    destroying the record that the rung existed — the same reasoning the subject vocabulary
    already follows for macro categories.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_levels(self, only_active: bool = False) -> list[ArchiveDescriptionLevel]:
        stmt = select(ArchiveDescriptionLevel).order_by(ArchiveDescriptionLevel.ordinal)
        if only_active:
            stmt = stmt.where(ArchiveDescriptionLevel.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def get(self, level_id: int) -> ArchiveDescriptionLevel | None:
        return self.db.get(ArchiveDescriptionLevel, level_id)

    def get_by_code(self, code: str) -> ArchiveDescriptionLevel | None:
        return self.db.scalars(select(ArchiveDescriptionLevel).where(ArchiveDescriptionLevel.code == code)).first()

    def get_by_ordinal(self, ordinal: int) -> ArchiveDescriptionLevel | None:
        return self.db.scalars(
            select(ArchiveDescriptionLevel).where(ArchiveDescriptionLevel.ordinal == ordinal)
        ).first()

    def create(self, command: CreateDescriptionLevelCommand) -> ArchiveDescriptionLevel:
        level = ArchiveDescriptionLevel(**command.model_dump())
        self.db.add(level)
        self.db.flush()
        return level

    def update(self, level: ArchiveDescriptionLevel, command: UpdateDescriptionLevelCommand) -> ArchiveDescriptionLevel:
        for field, value in command.model_dump(exclude_unset=True).items():
            setattr(level, field, value)
        self.db.flush()
        return level

    def document_counts(self) -> dict[int, int]:
        """How many descriptions point at each rung. Derived on read, never stored."""
        rows = self.db.execute(
            select(ArchiveDocument.level_id, func.count())
            .where(ArchiveDocument.level_id.is_not(None))
            .group_by(ArchiveDocument.level_id)
        ).all()
        return {int(level_id): int(count) for level_id, count in rows}

    def level_index(self) -> dict[str, int]:
        """``folded spelling -> level_id``, built once per call and reused across a batch."""
        return build_level_index(
            (level.level_id, level.name, list(level.aliases or [])) for level in self.list_levels()
        )

    def resolve(self, declared: str | None) -> int | None:
        """
        Resolves a declared spelling to a rung, or ``None`` when the catalogue does not know it.

        Returning ``None`` instead of guessing is what keeps a source typo from silently becoming
        a level: the caller decides whether an unknown value is a load that must not fail (the
        transfer) or a human error that must (the archivist review).
        """
        return resolve_level_id(self.level_index(), declared)

    def rules_by_id(self) -> dict[int, LevelRules]:
        """The rule slice of every rung, for the tree validation and the diagnostics."""
        return {
            level.level_id: LevelRules(
                level_id=level.level_id,
                ordinal=level.ordinal,
                name=level.name,
                requires_parent=level.requires_parent,
                allows_children=level.allows_children,
            )
            for level in self.list_levels()
        }

    def rules_by_code(self) -> dict[str, LevelRules]:
        return {
            level.code: LevelRules(
                level_id=level.level_id,
                ordinal=level.ordinal,
                name=level.name,
                requires_parent=level.requires_parent,
                allows_children=level.allows_children,
            )
            for level in self.list_levels()
        }

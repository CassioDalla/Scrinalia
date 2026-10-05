"""Level catalogue use cases (Fase 2.5, H1)."""

from memoria_curitibana.domains.archive.exceptions import (
    DescriptionLevelNotFoundError,
    DuplicateDescriptionLevelError,
    InvalidDescriptionLevelError,
)
from memoria_curitibana.domains.archive.models import ArchiveDescriptionLevel
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    CreateDescriptionLevelCommand,
    DescriptionLevelDTO,
    UpdateDescriptionLevelCommand,
)


class LevelCatalogService:
    """
    Owns the ladder of description levels.

    Nothing here deletes: a rung is deactivated, because the foreign key is ``SET NULL`` and
    deleting would unclassify every description pointing at it while destroying the record that
    the rung ever existed — the same rule the subject vocabulary already follows.
    """

    def __init__(self, repo: LevelCatalogRepository) -> None:
        self.repo = repo

    def list_levels(self, only_active: bool = False) -> list[DescriptionLevelDTO]:
        counts = self.repo.document_counts()
        return [
            DescriptionLevelDTO(
                level_id=level.level_id,
                ordinal=level.ordinal,
                code=level.code,
                name=level.name,
                description=level.description,
                aliases=list(level.aliases or []),
                requires_parent=level.requires_parent,
                allows_children=level.allows_children,
                is_active=level.is_active,
                document_count=counts.get(level.level_id, 0),
            )
            for level in self.repo.list_levels(only_active=only_active)
        ]

    def get_level(self, level_id: int) -> ArchiveDescriptionLevel:
        level = self.repo.get(level_id)
        if level is None:
            raise DescriptionLevelNotFoundError(f"Nível de descrição {level_id} não existe no catálogo.")
        return level

    def create_level(self, command: CreateDescriptionLevelCommand) -> DescriptionLevelDTO:
        """
        Registers a rung.

        The three uniqueness rules are checked here so the archivist gets a named conflict
        instead of a raw ``IntegrityError``; the database constraint still backs the check, since
        two concurrent requests can both pass it.
        """
        self._reject_collisions(command.ordinal, command.code, command.name)
        level = self.repo.create(command)
        return next(item for item in self.list_levels() if item.level_id == level.level_id)

    def update_level(self, level_id: int, command: UpdateDescriptionLevelCommand) -> DescriptionLevelDTO:
        level = self.get_level(level_id)

        if command.name is not None and command.name != level.name:
            self._reject_collisions(None, None, command.name)

        self.repo.update(level, command)
        return next(item for item in self.list_levels() if item.level_id == level.level_id)

    def resolve(self, declared: str | None) -> int | None:
        """Resolves a declared spelling, or ``None`` when the catalogue does not know it."""
        return self.repo.resolve(declared)

    def require(self, declared: str) -> int:
        """
        Resolves a spelling the *human* wrote, refusing the unknown ones.

        The asymmetry with ``resolve`` is deliberate: a staging payload with a level the catalogue
        does not know must not fail the load, but an archivist choosing a level is making a claim
        the catalogue has to be able to answer.
        """
        level_id = self.resolve(declared)
        if level_id is None:
            raise InvalidDescriptionLevelError(
                f"O nível de descrição '{declared}' não existe no catálogo. Cadastre-o (ou uma grafia equivalente) antes."
            )
        return level_id

    def _reject_collisions(self, ordinal: int | None, code: str | None, name: str | None) -> None:
        if ordinal is not None and self.repo.get_by_ordinal(ordinal) is not None:
            raise DuplicateDescriptionLevelError(f"Já existe um nível na posição {ordinal} da escada.")
        if code is not None and self.repo.get_by_code(code) is not None:
            raise DuplicateDescriptionLevelError(f"Já existe um nível com o código '{code}'.")
        if name is not None:
            for level in self.repo.list_levels():
                if level.name.strip().lower() == name.strip().lower():
                    raise DuplicateDescriptionLevelError(f"Já existe um nível chamado '{name}'.")

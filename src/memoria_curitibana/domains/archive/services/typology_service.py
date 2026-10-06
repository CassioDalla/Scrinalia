"""Typology catalogue use cases (Fase 4, the last catalogue without a screen)."""

from memoria_curitibana.domains.archive.exceptions import (
    DuplicateTypologyError,
    InvalidTypologyError,
    TypologyNotFoundError,
)
from memoria_curitibana.domains.archive.models import ArchiveTypology
from memoria_curitibana.domains.archive.repository.typology_repo import TypologyRepository
from memoria_curitibana.domains.archive.schemas.typology_schema import (
    CreateTypologyCommand,
    TypologyDTO,
    UpdateTypologyCommand,
)


class TypologyService:
    """
    Owns the typologies of the collection.

    Nothing here deletes: a typology is deactivated, because the foreign key is ``SET NULL`` and
    deleting would unclassify every description carrying it while destroying the record that the
    type ever existed — the same rule the level ladder and the subject vocabulary already follow.

    Deactivating is also the only lever that reaches the classifier: the zero-shot engine reads the
    active names as its candidate labels, so a retired type stops being proposed without a single
    classified description being touched.
    """

    def __init__(self, repo: TypologyRepository) -> None:
        self.repo = repo

    def list_typologies(self, only_active: bool = False) -> list[TypologyDTO]:
        counts = self.repo.document_counts()
        return [
            TypologyDTO(
                typology_id=typology.typology_id,
                name=typology.name,
                context_description=typology.context_description,
                is_active=typology.is_active,
                document_count=counts.get(typology.typology_id, 0),
            )
            for typology in self.repo.list_typologies(only_active=only_active)
        ]

    def get_typology(self, typology_id: int) -> ArchiveTypology:
        typology = self.repo.get(typology_id)
        if typology is None:
            raise TypologyNotFoundError(f"Tipologia documental {typology_id} não existe no catálogo.")
        return typology

    def create_typology(self, command: CreateTypologyCommand) -> TypologyDTO:
        """
        Registers a typology.

        The name uniqueness is checked here so the archivist gets a named conflict instead of a raw
        ``IntegrityError``; the database constraint still backs the check, since two concurrent
        requests can both pass it.
        """
        existing = self.repo.get_by_name(command.name)
        if existing is not None:
            raise DuplicateTypologyError(
                f"Já existe uma tipologia chamada '{existing.name}'. "
                "Se ela está desativada, reative-a em vez de criar outra."
            )

        typology = self.repo.create(command)
        return next(item for item in self.list_typologies() if item.typology_id == typology.typology_id)

    def update_typology(self, typology_id: int, command: UpdateTypologyCommand) -> TypologyDTO:
        typology = self.get_typology(typology_id)

        if command.name is not None:
            existing = self.repo.get_by_name(command.name)
            if existing is not None and existing.typology_id != typology_id:
                raise DuplicateTypologyError(f"Já existe uma tipologia chamada '{existing.name}'.")

        self.repo.update(typology, command)
        return next(item for item in self.list_typologies() if item.typology_id == typology_id)

    def require(self, typology_id: int) -> int:
        """
        Validates a typology a *human* chose, refusing the unknown ones.

        The asymmetry with the staging load is deliberate and identical to the level ladder's: a
        source payload the catalogue does not know must not fail a transfer, but an archivist
        choosing a typology is making a claim the catalogue has to be able to answer. Silently
        storing ``NULL`` would turn a wrong id into missing data.
        """
        if self.repo.get(typology_id) is None:
            raise InvalidTypologyError(
                f"A tipologia documental {typology_id} não existe no catálogo. "
                "Cadastre-a (ou escolha outra) antes de classificar a descrição."
            )
        return typology_id

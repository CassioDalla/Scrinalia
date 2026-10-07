"""
The collection vocabulary catalogue: what this archive declares, and the guard's input.

Nothing here is fixed by the software. The arrangement names and the non-subject terms are the
archivist's statement about *this* collection, which is why they are rows and not constants: the
reference installation seeds them, another institution replaces them, and an installation that
declares nothing gets an empty guard rather than Curitiba's names.

Two callers matter beyond the screen. The hierarchy proposal asks for ``arrangement_names()`` to
suggest a rung's name, and the subject guard asks for ``guard_vocabulary()`` — the value object
whose two sets decide whether a term is a place or a person. Both filter ``is_active``, so retiring
a row is what removes it from the AI's reach without erasing it from the catalogue.
"""

from scrinalia.domains.archive.domain.collection_vocabulary import CollectionVocabulary
from scrinalia.domains.archive.exceptions import (
    ArrangementTermNotFoundError,
    CollectionTermNotFoundError,
    DuplicateArrangementTermError,
    DuplicateCollectionTermError,
)
from scrinalia.domains.archive.models import ArchiveArrangementTerm, ArchiveCollectionTerm
from scrinalia.domains.archive.models.enums import CollectionTermKind
from scrinalia.domains.archive.repository.collection_vocabulary_repo import CollectionVocabularyRepository
from scrinalia.domains.archive.schemas.collection_vocabulary_schema import (
    ArrangementTermDTO,
    CollectionTermDTO,
    CollectionVocabularyResponse,
    CreateArrangementTermCommand,
    CreateCollectionTermCommand,
    UpdateArrangementTermCommand,
    UpdateCollectionTermCommand,
)


class CollectionVocabularyService:
    def __init__(self, repo: CollectionVocabularyRepository) -> None:
        self.repo = repo

    # =========================================================================
    # The reads the AI does
    # =========================================================================
    def arrangement_names(self) -> dict[str, str]:
        """``{token: display name}`` for the hierarchy proposal's suggestions."""
        return self.repo.arrangement_names()

    def guard_vocabulary(self) -> CollectionVocabulary:
        """The value object the subject guard consults for places and person names."""
        return self.repo.collection_vocabulary()

    # =========================================================================
    # The catalogue the curator edits
    # =========================================================================
    def read(self) -> CollectionVocabularyResponse:
        counts = self.repo.tag_counts()
        return CollectionVocabularyResponse(
            arrangement_terms=[
                ArrangementTermDTO(
                    term_id=term.term_id,
                    token=term.token,
                    display_name=term.display_name,
                    is_active=term.is_active,
                )
                for term in self.repo.list_arrangement_terms()
            ],
            collection_terms=[
                CollectionTermDTO(
                    term_id=term.term_id,
                    term=term.term,
                    kind=term.kind,
                    is_active=term.is_active,
                    tag_count=counts.get(term.term, 0),
                )
                for term in self.repo.list_collection_terms()
            ],
            kinds=list(CollectionTermKind),
        )

    def create_arrangement_term(self, command: CreateArrangementTermCommand) -> ArrangementTermDTO:
        """
        Registers a token-to-name suggestion.

        A token already taken — even by a retired row — is refused instead of overwritten: the
        retired row may be the one the archivist deactivated on purpose, and silently reviving it
        with another name would be worse than asking.
        """
        existing = self.repo.find_arrangement_term(command.token)
        if existing is not None:
            raise DuplicateArrangementTermError(
                f"O token '{existing.token}' já está no vocabulário como '{existing.display_name}'. "
                "Se ele está desativado, reative-o em vez de criar outro."
            )
        term = self.repo.create_arrangement_term(command)
        return ArrangementTermDTO(
            term_id=term.term_id, token=term.token, display_name=term.display_name, is_active=term.is_active
        )

    def update_arrangement_term(self, term_id: int, command: UpdateArrangementTermCommand) -> ArrangementTermDTO:
        term = self._require_arrangement_term(term_id)
        self.repo.update_arrangement_term(term, command)
        return ArrangementTermDTO(
            term_id=term.term_id, token=term.token, display_name=term.display_name, is_active=term.is_active
        )

    def create_collection_term(self, command: CreateCollectionTermCommand) -> CollectionTermDTO:
        existing = self.repo.find_collection_term(command.term, command.kind)
        if existing is not None:
            raise DuplicateCollectionTermError(f"O termo '{existing.term}' já está registrado como {existing.kind}.")
        term = self.repo.create_collection_term(command)
        return self._collection_dto(term)

    def update_collection_term(self, term_id: int, command: UpdateCollectionTermCommand) -> CollectionTermDTO:
        """
        Renames, re-kinds or (de)activates a term.

        Changing the spelling or the kind has to be checked against the target pair, or two rows
        could end up identical and the unique constraint would answer with a raw ``IntegrityError``
        instead of a named conflict.
        """
        term = self._require_collection_term(term_id)
        target_term = command.term if command.term is not None else term.term
        target_kind = command.kind if command.kind is not None else term.kind
        existing = self.repo.find_collection_term(target_term, target_kind)
        if existing is not None and existing.term_id != term_id:
            raise DuplicateCollectionTermError(f"O termo '{existing.term}' já está registrado como {existing.kind}.")

        self.repo.update_collection_term(term, command)
        return self._collection_dto(term)

    # =========================================================================
    # Internals
    # =========================================================================
    def _require_arrangement_term(self, term_id: int) -> ArchiveArrangementTerm:
        term = self.repo.get_arrangement_term(term_id)
        if term is None:
            raise ArrangementTermNotFoundError(f"O termo de arranjo {term_id} não existe no vocabulário.")
        return term

    def _require_collection_term(self, term_id: int) -> ArchiveCollectionTerm:
        term = self.repo.get_collection_term(term_id)
        if term is None:
            raise CollectionTermNotFoundError(f"O termo de acervo {term_id} não existe no vocabulário.")
        return term

    def _collection_dto(self, term: ArchiveCollectionTerm) -> CollectionTermDTO:
        return CollectionTermDTO(
            term_id=term.term_id,
            term=term.term,
            kind=term.kind,
            is_active=term.is_active,
            tag_count=self.repo.tag_counts().get(term.term, 0),
        )

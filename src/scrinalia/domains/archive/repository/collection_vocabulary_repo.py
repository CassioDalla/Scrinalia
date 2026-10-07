"""
Reads and edits the collection vocabulary: what *this* archive declares, not what the language is.

The read side is what the guard and the hierarchy proposal depend on, and it is deliberately
narrow: ``arrangement_names()`` returns the token-to-name map the proposal resolves a rung with,
and ``collection_vocabulary()`` returns the value object the guard is handed. Both filter
``is_active``, because that is the only lever that reaches the workers — a retired row stays
readable for the curator and invisible to the AI, exactly like a retired subject drawer.

The write side serves the catalogue screen. There is no ``delete``: removing a term would make the
guard accept it again (a silent behaviour change nobody asked for) and would erase the record that
the term was ever declared. ``is_active=false`` is the way out.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.domain.collection_vocabulary import (
    CollectionVocabulary,
    normalize_term,
    vocabulary_from_rows,
)
from scrinalia.domains.archive.domain.hierarchy_code import normalize_reference_code
from scrinalia.domains.archive.models import ArchiveArrangementTerm, ArchiveCollectionTerm, ArchiveTag
from scrinalia.domains.archive.schemas.collection_vocabulary_schema import (
    CreateArrangementTermCommand,
    CreateCollectionTermCommand,
    UpdateArrangementTermCommand,
    UpdateCollectionTermCommand,
)


class CollectionVocabularyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # =========================================================================
    # The reads the AI depends on
    # =========================================================================
    def arrangement_names(self) -> dict[str, str]:
        """
        ``{token: display name}`` of the active rows, for the hierarchy proposal.

        The whole map is loaded once per proposal: the alternative is a query per rung, and the
        catalogue is small by construction — a handful of tokens per collection.
        """
        stmt = select(ArchiveArrangementTerm.token, ArchiveArrangementTerm.display_name).where(
            ArchiveArrangementTerm.is_active.is_(True)
        )
        names: dict[str, str] = {}
        for token, display_name in self.db.execute(stmt).all():
            names[token] = display_name
        return names

    def collection_vocabulary(self) -> CollectionVocabulary:
        """The value object the subject guard is handed: the active terms, split by destination."""
        stmt = select(ArchiveCollectionTerm.term, ArchiveCollectionTerm.kind).where(
            ArchiveCollectionTerm.is_active.is_(True)
        )
        rows = [(term, kind.value) for term, kind in self.db.execute(stmt).all()]
        return vocabulary_from_rows(rows)

    # =========================================================================
    # The catalogue reads the screen shows
    # =========================================================================
    def list_arrangement_terms(self, only_active: bool = False) -> list[ArchiveArrangementTerm]:
        stmt = select(ArchiveArrangementTerm).order_by(ArchiveArrangementTerm.token)
        if only_active:
            stmt = stmt.where(ArchiveArrangementTerm.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def list_collection_terms(self, only_active: bool = False) -> list[ArchiveCollectionTerm]:
        stmt = select(ArchiveCollectionTerm).order_by(ArchiveCollectionTerm.term)
        if only_active:
            stmt = stmt.where(ArchiveCollectionTerm.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def get_arrangement_term(self, term_id: int) -> ArchiveArrangementTerm | None:
        return self.db.get(ArchiveArrangementTerm, term_id)

    def get_collection_term(self, term_id: int) -> ArchiveCollectionTerm | None:
        return self.db.get(ArchiveCollectionTerm, term_id)

    def find_arrangement_term(self, token: str) -> ArchiveArrangementTerm | None:
        return self.db.scalars(
            select(ArchiveArrangementTerm).where(ArchiveArrangementTerm.token == normalize_reference_code(token))
        ).first()

    def find_collection_term(self, term: str, kind: str) -> ArchiveCollectionTerm | None:
        return self.db.scalars(
            select(ArchiveCollectionTerm).where(
                ArchiveCollectionTerm.term == normalize_term(term),
                ArchiveCollectionTerm.kind == kind,
            )
        ).first()

    def tag_counts(self) -> dict[str, int]:
        """
        ``{tag name: how many tags carry it}`` for the whole taxonomy.

        The catalogue's terms are matched by *spelling* — there is no foreign key between a term and
        a tag — so the weight of a term is the weight of its spelling. One grouped query for the
        page instead of one per row: 8k rows is cheap, 8k queries is not.
        """
        rows = self.db.execute(
            select(func.lower(ArchiveTag.name), func.count()).group_by(func.lower(ArchiveTag.name))
        ).all()
        return {name: int(count) for name, count in rows}

    # =========================================================================
    # Writes
    # =========================================================================
    def create_arrangement_term(self, command: CreateArrangementTermCommand) -> ArchiveArrangementTerm:
        term = ArchiveArrangementTerm(
            token=normalize_reference_code(command.token),
            display_name=command.display_name.strip(),
        )
        self.db.add(term)
        self.db.flush()
        return term

    def update_arrangement_term(
        self, term: ArchiveArrangementTerm, command: UpdateArrangementTermCommand
    ) -> ArchiveArrangementTerm:
        for field, value in command.model_dump(exclude_unset=True).items():
            setattr(term, field, value)
        self.db.flush()
        return term

    def create_collection_term(self, command: CreateCollectionTermCommand) -> ArchiveCollectionTerm:
        term = ArchiveCollectionTerm(term=normalize_term(command.term), kind=command.kind)
        self.db.add(term)
        self.db.flush()
        return term

    def update_collection_term(
        self, term: ArchiveCollectionTerm, command: UpdateCollectionTermCommand
    ) -> ArchiveCollectionTerm:
        changes = command.model_dump(exclude_unset=True)
        if "term" in changes:
            changes["term"] = normalize_term(changes["term"])
        for field, value in changes.items():
            setattr(term, field, value)
        self.db.flush()
        return term

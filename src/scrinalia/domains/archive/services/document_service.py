from collections.abc import Callable

from scrinalia.core.author import Author
from scrinalia.domains.archive.engines.base import EmbeddingEngine
from scrinalia.domains.archive.exceptions import DocumentHasChildrenError, DocumentNotFoundError
from scrinalia.domains.archive.ports.document import DocumentRepositoryPort
from scrinalia.domains.archive.schemas.command_schema import (
    DocumentReviewCommand,
    EntityLinkCommand,
    TagLinkCommand,
)
from scrinalia.domains.archive.schemas.document_schema import (
    DocumentDeletionDTO,
    DocumentDeletionListResponse,
    DocumentListResponse,
    DocumentRevisionDTO,
    DocumentSummary,
)
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery
from scrinalia.domains.archive.services.level_catalog_service import LevelCatalogService
from scrinalia.domains.archive.services.typology_service import TypologyService


class DocumentService:
    """
    Service for reading and human curation of the collection (Archive layer).

    Isolates the API and the front-end from direct database access: all
    navigation (showcase) and human editing go through here.

    A semantic search needs the query embedded before it reaches the repository, so the
    service receives an embedder **factory** instead of an engine: the model is heavy and
    must only be built when a semantic request actually arrives, never on a lexical one.
    """

    def __init__(
        self,
        repo: DocumentRepositoryPort,
        embedder: Callable[[], EmbeddingEngine] | None = None,
        levels: LevelCatalogService | None = None,
        typologies: TypologyService | None = None,
    ) -> None:
        self.repo = repo
        self._embedder = embedder
        self._engine: EmbeddingEngine | None = None
        self._levels = levels
        self._typologies = typologies

    def _get_engine(self) -> EmbeddingEngine:
        """Builds (once per service) the embedding engine, on first semantic search."""
        if self._engine is None:
            if self._embedder is None:
                raise RuntimeError("Semantic search requires an embedding engine.")
            self._engine = self._embedder()
        return self._engine

    def search(self, query: DocumentSearchQuery) -> DocumentListResponse:
        query_embedding = None

        if query.mode == "semantic" and query.term and query.term.strip():
            query_embedding = self._get_engine().embed([query.term])[0]

        docs, total, facets = self.repo.search(query, query_embedding=query_embedding)
        return DocumentListResponse(
            total=total, limit=query.limit, offset=query.offset, items=list(docs), facets=facets
        )

    def get(self, description_id: str) -> DocumentSummary:
        doc = self.repo.get_by_id(description_id)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return doc

    def get_published(self, description_id: str) -> DocumentSummary:
        """
        One description, but only when the institution cleared it for diffusion.

        A record that is not published raises the same not-found error the diffusion surface already
        maps to 404, rather than a distinct "forbidden": telling the two apart would confirm that
        the description exists, which is exactly the fact the gate protects.
        """
        doc = self.get(description_id)
        if not doc.is_published:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return doc

    def list_revisions(self, description_id: str) -> list[DocumentRevisionDTO]:
        """Human review audit trail of one document."""
        return self.repo.list_revisions(description_id)

    def update_review(self, command: DocumentReviewCommand) -> DocumentSummary:
        """
        Applies the archivist's edit, refusing a level or a typology the catalogue does not know.

        The asymmetry with the staging load is deliberate: a payload with an unknown level is
        recorded as unclassified and the transfer carries on, but an archivist choosing a rung is
        making a claim the catalogue has to be able to answer. Silently storing ``NULL`` would turn
        a wrong id into missing data.
        """
        if command.level_id is not None and self._levels is not None:
            self._levels.get_level(command.level_id)
        if command.typology_id is not None and self._typologies is not None:
            self._typologies.require(command.typology_id)

        doc = self.repo.update_review(command)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{command.description_id}' não encontrado no acervo.")
        return doc

    # --- Local curation of one document's subjects -------------------------------------------
    #
    # These four answer the oldest gap of the curation phase: the taxonomy routes merge terms
    # globally, but "this document is about this too" could only be decided by re-running a
    # worker. Like every human write here, they take the record out of the AI's reach — which is
    # why they all funnel into the same revision ledger.
    def link_tag(
        self, command: TagLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary:
        """Attaches a tag to one description as a human decision."""
        return self._require(self.repo.link_tag(command, changed_by, note), command.description_id)

    def unlink_tag(
        self, command: TagLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary:
        """Detaches a tag from one description as a human decision."""
        return self._require(self.repo.unlink_tag(command, changed_by, note), command.description_id)

    def link_entity(
        self, command: EntityLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary:
        """Attaches a named entity to one description as a human decision."""
        return self._require(self.repo.link_entity(command, changed_by, note), command.description_id)

    def unlink_entity(
        self, command: EntityLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary:
        """Detaches a named entity from one description as a human decision."""
        return self._require(self.repo.unlink_entity(command, changed_by, note), command.description_id)

    # --- Deletion: the only write here that removes a record ------------------------------------
    def delete(
        self, description_id: str, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentDeletionDTO:
        """
        Removes one description for good, after snapshotting it into the deletion ledger.

        The guard is the arrangement's integrity, not a courtesy: a node with children cannot be
        deleted, because every descendant's materialised ``path`` carries its ancestors' ids and the
        FK is ``RESTRICT`` for exactly that reason. A subtree would be left pointing at a prefix that no
        longer exists, and the tree's navigation (``path LIKE 'x.%'``) would answer nothing for a branch
        that still shows descriptions in it.

        What the archivist is told is where to go: delete the children first, or move them.
        """
        children = self.repo.count_children(description_id)
        if children > 0:
            raise DocumentHasChildrenError(
                f"'{description_id}' tem {children} descrição(ões) abaixo dela. Exclua ou mova os filhos "
                "primeiro: a árvore não pode ficar apontando para um ramo que não existe."
            )

        entry = self.repo.delete_document(description_id, changed_by=changed_by, note=note)
        if entry is None:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return entry

    def list_deletions(self, term: str | None = None, limit: int = 50, offset: int = 0) -> DocumentDeletionListResponse:
        """One page of the deletion ledger, newest first, optionally filtered by a term."""
        items, total = self.repo.list_deletions(term, limit, offset)
        return DocumentDeletionListResponse(total=total, limit=limit, offset=offset, items=list(items))

    @staticmethod
    def _require(doc: DocumentSummary | None, description_id: str) -> DocumentSummary:
        """Turns the repository's "no such document" into the business error the API maps to 404."""
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return doc

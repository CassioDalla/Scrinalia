from collections.abc import Callable

from memoria_curitibana.domains.archive.engines.base import EmbeddingEngine
from memoria_curitibana.domains.archive.exceptions import DocumentNotFoundError
from memoria_curitibana.domains.archive.ports.document import DocumentRepositoryPort
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.document_schema import (
    DocumentListResponse,
    DocumentRevisionDTO,
    DocumentSummary,
)
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery
from memoria_curitibana.domains.archive.services.level_catalog_service import LevelCatalogService


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
    ) -> None:
        self.repo = repo
        self._embedder = embedder
        self._engine: EmbeddingEngine | None = None
        self._levels = levels

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

        docs, total = self.repo.search(query, query_embedding=query_embedding)
        return DocumentListResponse(total=total, limit=query.limit, offset=query.offset, items=list(docs))

    def get(self, description_id: str) -> DocumentSummary:
        doc = self.repo.get_by_id(description_id)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return doc

    def list_revisions(self, description_id: str) -> list[DocumentRevisionDTO]:
        """Human review audit trail of one document."""
        return self.repo.list_revisions(description_id)

    def update_review(self, command: DocumentReviewCommand) -> DocumentSummary:
        """
        Applies the archivist's edit, refusing a level the catalogue does not know.

        The asymmetry with the staging load is deliberate: a payload with an unknown level is
        recorded as unclassified and the transfer carries on, but an archivist choosing a rung is
        making a claim the catalogue has to be able to answer. Silently storing ``NULL`` would turn
        a wrong id into missing data.
        """
        if command.level_id is not None and self._levels is not None:
            self._levels.get_level(command.level_id)

        doc = self.repo.update_review(command)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{command.description_id}' não encontrado no acervo.")
        return doc

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
    ) -> None:
        self.repo = repo
        self._embedder = embedder
        self._engine: EmbeddingEngine | None = None

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
        doc = self.repo.update_review(command)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{command.description_id}' não encontrado no acervo.")
        return doc

"""Composition root of the HTTP layer: one transaction and its services per request."""

from collections.abc import Iterator
from functools import lru_cache

from litestar.di import NamedDependency

from memoria_curitibana.core.database import create_session
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.archive.engines.base import EmbeddingEngine
from memoria_curitibana.domains.archive.repository.cleaning_repo import CleaningRepository
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.repository.entity_repo import EntityRepository
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository
from memoria_curitibana.domains.archive.repository.text_quality_repo import TextQualityRepository
from memoria_curitibana.domains.archive.services.cleaning_service import CleaningService
from memoria_curitibana.domains.archive.services.document_service import DocumentService
from memoria_curitibana.domains.archive.services.entity_service import EntityService
from memoria_curitibana.domains.archive.services.tag_service import TagService
from memoria_curitibana.domains.archive.services.text_quality_service import TextQualityService


@lru_cache(maxsize=1)
def provide_embedding_engine() -> EmbeddingEngine:
    """
    Process-wide embedding engine used by semantic search.

    Cached on purpose: loading the model costs seconds and hundreds of MB, and it must
    happen at most once per process, only when the first semantic request arrives. The
    registry is imported here so a lexical request never pays the engine import either.
    """
    from memoria_curitibana.domains.archive.engines.embeddings.registry import get_engine

    return get_engine("sentence_transformer", preset="multilingual_minilm")


def provide_unit_of_work() -> Iterator[UnitOfWork]:
    """
    Owns the request transaction.

    Repositories and services only ``flush``: this dependency commits once the
    handler has succeeded and rolls back when it raised, so the HTTP layer follows
    the same transaction rule as the workers.
    """
    with create_session() as db:
        unit_of_work = UnitOfWork(db)
        try:
            yield unit_of_work
        except BaseException:
            unit_of_work.rollback()
            raise
        else:
            unit_of_work.commit()


def provide_tag_service(unit_of_work: NamedDependency[UnitOfWork]) -> TagService:
    """Builds the service over the repositories bound to the request transaction."""
    tag_repo = TagRepository(unit_of_work.db)
    doc_repo = DocumentRepository(unit_of_work.db)

    return TagService(tag_repo, doc_repo)


def provide_entity_service(unit_of_work: NamedDependency[UnitOfWork]) -> EntityService:
    """Builds the Entity service by injecting its repository."""
    return EntityService(EntityRepository(unit_of_work.db))


def provide_cleaning_service(unit_of_work: NamedDependency[UnitOfWork]) -> CleaningService:
    """Builds the cleaning service by injecting its repository."""
    return CleaningService(CleaningRepository(unit_of_work.db))


def provide_text_quality_service(unit_of_work: NamedDependency[UnitOfWork]) -> TextQualityService:
    """Builds the repeated-excerpt curation service over the request transaction."""
    return TextQualityService(TextQualityRepository(unit_of_work.db))


def provide_document_service(unit_of_work: NamedDependency[UnitOfWork]) -> DocumentService:
    """Builds the collection reading/curation service with the request transaction."""
    return DocumentService(DocumentRepository(unit_of_work.db), embedder=provide_embedding_engine)

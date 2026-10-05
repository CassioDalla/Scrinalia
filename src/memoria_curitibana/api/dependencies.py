"""Composition root of the HTTP layer: one transaction and its services per request."""

from collections.abc import Iterator
from functools import lru_cache

from litestar.di import NamedDependency

from memoria_curitibana.core.database import create_session
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.archive.engines.base import EmbeddingEngine
from memoria_curitibana.domains.archive.repository.cleaning_repo import CleaningRepository
from memoria_curitibana.domains.archive.repository.curation_repo import CurationRepository
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.repository.entity_repo import EntityRepository
from memoria_curitibana.domains.archive.repository.hierarchy_repo import HierarchyRepository
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository
from memoria_curitibana.domains.archive.repository.text_quality_repo import TextQualityRepository
from memoria_curitibana.domains.archive.services.cleaning_service import CleaningService
from memoria_curitibana.domains.archive.services.curation_service import CurationService
from memoria_curitibana.domains.archive.services.document_service import DocumentService
from memoria_curitibana.domains.archive.services.entity_service import EntityService
from memoria_curitibana.domains.archive.services.hierarchy_materialisation_service import (
    HierarchyMaterialisationService,
)
from memoria_curitibana.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService
from memoria_curitibana.domains.archive.services.hierarchy_service import HierarchyService
from memoria_curitibana.domains.archive.services.level_catalog_service import LevelCatalogService
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


def provide_curation_service(unit_of_work: NamedDependency[UnitOfWork]) -> CurationService:
    """Builds the curator's work list over the request transaction; it only reads."""
    return CurationService(CurationRepository(unit_of_work.db))


def provide_document_service(unit_of_work: NamedDependency[UnitOfWork]) -> DocumentService:
    """Builds the collection reading/curation service with the request transaction."""
    db = unit_of_work.db
    return DocumentService(
        DocumentRepository(db),
        embedder=provide_embedding_engine,
        # The human review resolves ``level_id`` through the catalogue, so a wrong rung is a named
        # business error instead of an integrity error surfacing as a conflict.
        levels=LevelCatalogService(LevelCatalogRepository(db)),
    )


def provide_level_catalog_service(unit_of_work: NamedDependency[UnitOfWork]) -> LevelCatalogService:
    """Builds the level catalogue service over the request transaction."""
    return LevelCatalogService(LevelCatalogRepository(unit_of_work.db))


def provide_hierarchy_service(unit_of_work: NamedDependency[UnitOfWork]) -> HierarchyService:
    """Builds the tree service with both repositories bound to the request transaction."""
    db = unit_of_work.db
    return HierarchyService(HierarchyRepository(db), LevelCatalogRepository(db))


def provide_hierarchy_proposal_service(unit_of_work: NamedDependency[UnitOfWork]) -> HierarchyProposalService:
    """Builds the read-only proposal service; it shares the transaction and never writes."""
    db = unit_of_work.db
    return HierarchyProposalService(HierarchyRepository(db), LevelCatalogRepository(db))


def provide_hierarchy_materialisation_service(
    unit_of_work: NamedDependency[UnitOfWork],
) -> HierarchyMaterialisationService:
    """Builds the materialisation service over the request transaction, proposal included."""
    db = unit_of_work.db
    repo = HierarchyRepository(db)
    catalog = LevelCatalogRepository(db)
    return HierarchyMaterialisationService(repo, catalog, HierarchyProposalService(repo, catalog))

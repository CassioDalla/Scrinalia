from sqlalchemy.orm import Session

from domains.archive.repository.cleaning_repo import CleaningRepository
from domains.archive.repository.document_repo import DocumentRepository
from domains.archive.repository.entity_repo import EntityRepository
from domains.archive.repository.tag_repo import TagRepository
from domains.archive.services.cleaning_service import CleaningService
from domains.archive.services.document_service import DocumentService
from domains.archive.services.entity_service import EntityService
from domains.archive.services.tag_service import TagService


def provide_tag_service(db_session: Session) -> TagService:
    """Builds the service by injecting the repositories created with the current request session."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)

    return TagService(tag_repo, doc_repo)


def provide_entity_service(db_session: Session) -> EntityService:
    """Builds the Entity service by injecting its repository."""
    repo = EntityRepository(db_session)
    return EntityService(repo)


def provide_cleaning_service(db_session: Session) -> CleaningService:
    return CleaningService(CleaningRepository(db_session))


def provide_document_service(db_session: Session) -> DocumentService:
    """Builds the collection reading/curation service with the request session."""
    return DocumentService(DocumentRepository(db_session))

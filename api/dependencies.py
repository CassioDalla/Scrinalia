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
    """Constrói o serviço injetando os repositórios criados com a sessão da requisição atual."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)

    return TagService(tag_repo, doc_repo)


def provide_entity_service(db_session: Session) -> EntityService:
    """Constrói o serviço de Entidades injetando o seu repositório."""
    repo = EntityRepository(db_session)
    return EntityService(repo)


def provide_cleaning_service(db_session: Session) -> CleaningService:
    return CleaningService(CleaningRepository(db_session))


def provide_document_service(db_session: Session) -> DocumentService:
    """Constrói o serviço de leitura/curadoria do acervo com a sessão da requisição."""
    return DocumentService(DocumentRepository(db_session))
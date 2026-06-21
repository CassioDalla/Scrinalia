from sqlalchemy.orm import Session

from domains.archive.services.tag_service import TagService


def provide_tag_service(db_session: Session) -> TagService:
    """Constrói o serviço injetando a sessão do banco da requisição atual."""
    return TagService(db_session)

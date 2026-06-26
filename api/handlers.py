from litestar import Request, Response
from litestar.status_codes import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from sqlalchemy.exc import IntegrityError

from domains.archive.exceptions import (
    DomainException,
    EngineExecutionError,
    InvalidMergeError,
    InvalidParam,
    TagNotFoundError,
)


def domain_exception_handler(request: Request, exc: DomainException) -> Response:
    """
    Mapeia dinamicamente as exceções do Core do negócio para os
    status codes corretos do protocolo HTTP.
    """
    # Define um erro padrão caso a exceção específica não esteja mapeada
    status_code = HTTP_400_BAD_REQUEST

    if isinstance(exc, TagNotFoundError):
        status_code = HTTP_404_NOT_FOUND

    elif isinstance(exc, (InvalidParam, InvalidMergeError)):
        status_code = HTTP_400_BAD_REQUEST

    elif isinstance(exc, EngineExecutionError):
        status_code = HTTP_422_UNPROCESSABLE_ENTITY

    # Estrutura de resposta padronizada para o Front-end
    return Response(
        content={
            "error_code": exc.__class__.__name__,
            "message": str(exc),
        },
        status_code=status_code,
    )


def integrity_error_handler(request: Request, exc: IntegrityError) -> Response:
    """Captura conflitos estruturais do PostgreSQL (ex: violação de Unique, Foreign Key)."""
    return Response(
        content={
            "error_code": "IntegrityError",
            "message": "Conflito estrutural no banco de dados. Operação abortada.",
        },
        status_code=HTTP_409_CONFLICT,
    )


def value_error_handler(request: Request, exc: ValueError) -> Response:
    """Captura validações nativas do Python lançadas pelos Services."""
    return Response(
        content={"error_code": "ValueError", "message": str(exc)},
        status_code=HTTP_400_BAD_REQUEST,
    )

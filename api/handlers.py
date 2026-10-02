from litestar import Request, Response
from litestar.status_codes import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from sqlalchemy.exc import IntegrityError

from domains.archive.exceptions import (
    DocumentNotFoundError,
    DomainException,
    EngineExecutionError,
    InvalidMergeError,
    InvalidParam,
    TagNotFoundError,
)


def domain_exception_handler(request: Request, exc: DomainException) -> Response:
    """
    Dynamically maps business Core exceptions to the
    correct HTTP protocol status codes.
    """
    # Defines a default error in case the specific exception is not mapped
    status_code = HTTP_400_BAD_REQUEST

    if isinstance(exc, (TagNotFoundError, DocumentNotFoundError)):
        status_code = HTTP_404_NOT_FOUND

    elif isinstance(exc, (InvalidParam, InvalidMergeError)):
        status_code = HTTP_400_BAD_REQUEST

    elif isinstance(exc, EngineExecutionError):
        status_code = HTTP_422_UNPROCESSABLE_ENTITY

    # Standardized response structure for the Front-end
    return Response(
        content={
            "error_code": exc.__class__.__name__,
            "message": str(exc),
        },
        status_code=status_code,
    )


def integrity_error_handler(request: Request, exc: IntegrityError) -> Response:
    """Captures structural PostgreSQL conflicts (e.g.: Unique, Foreign Key violation)."""
    return Response(
        content={
            "error_code": "IntegrityError",
            "message": "Conflito estrutural no banco de dados. Operação abortada.",
        },
        status_code=HTTP_409_CONFLICT,
    )


def value_error_handler(request: Request, exc: ValueError) -> Response:
    """Captures native Python validations raised by the Services."""
    return Response(
        content={"error_code": "ValueError", "message": str(exc)},
        status_code=HTTP_400_BAD_REQUEST,
    )

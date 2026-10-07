from litestar import Request, Response
from litestar.status_codes import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from sqlalchemy.exc import IntegrityError

from memoria_curitibana.api.middleware import request_id_of
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.exceptions import (
    CleaningRuleNotFoundError,
    ConflictResolutionAlreadyUndoneError,
    ConflictResolutionNotFoundError,
    DescriptionLevelNotFoundError,
    DocumentHasChildrenError,
    DocumentNotFoundError,
    DomainException,
    DuplicateDescriptionLevelError,
    DuplicateTypologyError,
    EngineExecutionError,
    EntityNotFoundError,
    HierarchyNodeNotFoundError,
    HierarchyPlanNotFoundError,
    InvalidDescriptionLevelError,
    InvalidHierarchyMoveError,
    InvalidHierarchyPlanError,
    InvalidMergeError,
    InvalidParam,
    InvalidTypologyError,
    InvalidWorkerSettingsError,
    MacroCategoryNotFoundError,
    MaterialisationAlreadyUndoneError,
    MaterialisationNotFoundError,
    MergeAlreadyUndoneError,
    MergeLogNotFoundError,
    TagMergeProposalNotFoundError,
    TagNotFoundError,
    TextTemplateNotFoundError,
    TypologyNotFoundError,
    UnresolvableConflictError,
    WorkerNotFoundError,
    WorkerRunAlreadyActiveError,
    WorkerRunNotFoundError,
)
from memoria_curitibana.domains.archive.repository.api_error_repo import ApiErrorRecorder

#: One recorder for the process. It opens its own short-lived session per write, so this instance
#: keeps nothing between requests and needs no per-request wiring.
_api_error_recorder = ApiErrorRecorder()


def domain_exception_handler(request: Request, exc: DomainException) -> Response:
    """
    Dynamically maps business Core exceptions to the
    correct HTTP protocol status codes.
    """
    # Defines a default error in case the specific exception is not mapped
    status_code = HTTP_400_BAD_REQUEST

    if isinstance(
        exc,
        (
            TagNotFoundError,
            TagMergeProposalNotFoundError,
            EntityNotFoundError,
            MergeLogNotFoundError,
            DocumentNotFoundError,
            CleaningRuleNotFoundError,
            MacroCategoryNotFoundError,
            TextTemplateNotFoundError,
            DescriptionLevelNotFoundError,
            TypologyNotFoundError,
            ConflictResolutionNotFoundError,
            HierarchyNodeNotFoundError,
            HierarchyPlanNotFoundError,
            MaterialisationNotFoundError,
            WorkerNotFoundError,
            WorkerRunNotFoundError,
        ),
    ):
        status_code = HTTP_404_NOT_FOUND

    elif isinstance(
        exc,
        (
            MergeAlreadyUndoneError,
            DuplicateDescriptionLevelError,
            DuplicateTypologyError,
            MaterialisationAlreadyUndoneError,
            ConflictResolutionAlreadyUndoneError,
            DocumentHasChildrenError,
            WorkerRunAlreadyActiveError,
        ),
    ):
        status_code = HTTP_409_CONFLICT

    elif isinstance(exc, (InvalidParam, InvalidMergeError)):
        status_code = HTTP_400_BAD_REQUEST

    elif isinstance(
        exc,
        (
            EngineExecutionError,
            InvalidDescriptionLevelError,
            InvalidHierarchyMoveError,
            InvalidHierarchyPlanError,
            InvalidTypologyError,
            UnresolvableConflictError,
            InvalidWorkerSettingsError,
        ),
    ):
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


def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """
    The last handler: an unexpected failure is recorded and answered in the shape clients already know.

    Only genuinely unexpected exceptions reach here. ``DomainException`` and ``IntegrityError`` have
    handlers of their own and Litestar picks the more specific one first, because a 404 or a 409 is an
    *answer* the API owes a client, not a defect. ``HTTPException`` (404, 405) keeps Litestar's
    default for the same reason — overriding it would turn "no such route" into a recorded incident.

    The response says nothing about the cause: the API is unauthenticated today, and the exception
    text of a programming mistake is not something to publish. What ties the sentence the archivist
    reads to the traceback is the request id, which the middleware put in the response header.
    """
    path = str(request.scope.get("path") or "")
    request_id = request_id_of(request.scope)
    logger.opt(exception=exc).error(f"💥 Falha não tratada em {request.method} {path}: {exc}")

    _api_error_recorder.record(
        request_id=request_id,
        method=request.method,
        path=path,
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        exc=exc,
    )

    return Response(
        content={
            "error_code": "InternalError",
            "message": "Erro interno inesperado. A falha foi registrada e pode ser localizada pela referência.",
        },
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
    )

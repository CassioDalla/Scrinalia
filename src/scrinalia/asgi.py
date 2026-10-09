"""Litestar application factory, importable without the deployable entrypoint."""

from typing import Any

from litestar import Litestar
from litestar.di import Provide
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.logging import LoggingConfig
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from sqlalchemy.exc import IntegrityError

from scrinalia.api.controllers.auth_controller import AuthController
from scrinalia.api.controllers.cleaning_controller import CleaningController
from scrinalia.api.controllers.collection_vocabulary_controller import CollectionVocabularyController
from scrinalia.api.controllers.curation_controller import CurationController
from scrinalia.api.controllers.document_controller import DocumentController
from scrinalia.api.controllers.health_controller import HealthController
from scrinalia.api.controllers.hierarchy_controller import HierarchyController
from scrinalia.api.controllers.public_controller import PublicController
from scrinalia.api.controllers.setup_controller import SetupController
from scrinalia.api.controllers.system_controller import SystemController
from scrinalia.api.controllers.taxonomy_controller import TaxonomyController
from scrinalia.api.controllers.text_quality_controller import TextQualityController
from scrinalia.api.controllers.typology_controller import TypologyController
from scrinalia.api.controllers.users_controller import UsersController
from scrinalia.api.dependencies import provide_unit_of_work
from scrinalia.api.handlers import (
    domain_exception_handler,
    integrity_error_handler,
    not_authorized_handler,
    permission_denied_handler,
    unhandled_exception_handler,
)
from scrinalia.api.lifespan import application_lifespan
from scrinalia.api.middleware import RequestContextMiddleware
from scrinalia.api.security import access_guard, origin_guard
from scrinalia.api.spa import curator_spa_router
from scrinalia.core.config import settings
from scrinalia.core.logger import InterceptHandler, intercept_stdlib_logging
from scrinalia.domains.archive.exceptions import DomainException


def _logging_config() -> LoggingConfig:
    """
    Keeps the loguru sinks as the single destination.

    Litestar and uvicorn both apply a ``dictConfig`` at startup, which would replace
    the stdlib handlers built by ``core.logger``. Wiring only the intercept handler
    into Litestar preserves both the sinks and Litestar's own schema warnings.
    """
    return LoggingConfig(
        loggers={"litestar": {"level": settings.LOG_LEVEL, "handlers": ["intercept"], "propagate": False}},
        root={"level": settings.LOG_LEVEL, "handlers": ["intercept"]},
        handlers={"intercept": {"class": InterceptHandler}},
        configure_root_logger=True,
        disable_existing_loggers=False,
    )


def create_app() -> Litestar:
    """Builds the ASGI application. Tests and tooling should use this factory."""
    route_handlers: list[Any] = [
        # First: ``/health/*`` is the one route that must never be reached through the SPA's
        # ``html_mode`` catch-all, and the static router is appended last precisely so it cannot be.
        HealthController,
        # Second: the only routes reachable without a session are declared here, and ``/api/v1/auth``
        # is where the session comes from. Registering it early keeps the login out of the reach of
        # anything that might later be added in front of it.
        AuthController,
        # The other anonymous surface, and the narrower one: it works only while the installation has
        # no account at all, and answers 409 forever after (ADR 0011). Registered beside the login
        # because the two are the whole of what an anonymous client can reach on purpose.
        SetupController,
        TaxonomyController,
        CleaningController,
        CollectionVocabularyController,
        CurationController,
        DocumentController,
        HierarchyController,
        PublicController,
        SystemController,
        TextQualityController,
        TypologyController,
        # The accounts: the surface of ``Permission.ADMIN``, which is where the menu's
        # "Configurações" group lands. Registered with the rest — it declares its own permission on
        # every operation like any other controller.
        UsersController,
    ]

    if (spa := curator_spa_router()) is not None:
        route_handlers.append(spa)

    return Litestar(
        route_handlers=route_handlers,
        # The request id is minted before anything else, so the access line of a refused request
        # carries it too.
        middleware=[RequestContextMiddleware()],
        # Two guards for every route, and they answer different questions. ``origin_guard`` runs
        # first because it is the cheapest — it reads two headers and touches no database — and it
        # refuses a cross-origin mutation before the session is even resolved. ``access_guard`` then
        # authenticates from the session cookie and enforces the role each operation declares in its
        # own ``opt``. Registered per controller either would leak into routes that must not have it,
        # because Litestar guards are cumulative and a route cannot relax what its controller
        # declared.
        guards=[origin_guard, access_guard],
        dependencies={"unit_of_work": Provide(provide_unit_of_work)},
        exception_handlers={
            DomainException: domain_exception_handler,
            IntegrityError: integrity_error_handler,
            # Registered **by class**, which is safe here: neither is in the MRO of the framework's
            # 404, so they cannot turn "no such route" into a recorded incident. They exist to answer
            # 401/403 in the shape the front already reads (``error_code``/``message``).
            NotAuthorizedException: not_authorized_handler,
            PermissionDeniedException: permission_denied_handler,
            # Registered under the **status code**, not under ``Exception``. Litestar resolves a
            # handler by walking the exception's MRO and only then falling back to the 500 key, and
            # ``Exception`` is in the MRO of every ``HTTPException`` — registering it by class would
            # shadow the framework's own 404/405 answer and turn "no such route" into a 500. The
            # status key is consulted *only* for exceptions that are not ``HTTPException``, which is
            # exactly the boundary between an answer and a defect.
            HTTP_500_INTERNAL_SERVER_ERROR: unhandled_exception_handler,
        },
        lifespan=[application_lifespan],
        logging_config=_logging_config(),
        debug=settings.DEBUG,
    )


app = create_app()

# Uvicorn's own ``dictConfig`` runs after this and does not disable existing loggers,
# so this handler also survives for the records that do not originate from Litestar.
intercept_stdlib_logging()

__all__ = ["app", "create_app"]

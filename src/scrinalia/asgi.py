"""Litestar application factory, importable without the deployable entrypoint."""

from typing import Any

from litestar import Litestar
from litestar.di import Provide
from litestar.logging import LoggingConfig
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from sqlalchemy.exc import IntegrityError

from scrinalia.api.controllers.cleaning_controller import CleaningController
from scrinalia.api.controllers.curation_controller import CurationController
from scrinalia.api.controllers.document_controller import DocumentController
from scrinalia.api.controllers.health_controller import HealthController
from scrinalia.api.controllers.hierarchy_controller import HierarchyController
from scrinalia.api.controllers.public_controller import PublicController
from scrinalia.api.controllers.system_controller import SystemController
from scrinalia.api.controllers.taxonomy_controller import TaxonomyController
from scrinalia.api.controllers.text_quality_controller import TextQualityController
from scrinalia.api.controllers.typology_controller import TypologyController
from scrinalia.api.dependencies import provide_unit_of_work
from scrinalia.api.handlers import (
    domain_exception_handler,
    integrity_error_handler,
    unhandled_exception_handler,
)
from scrinalia.api.lifespan import application_lifespan
from scrinalia.api.middleware import RequestContextMiddleware
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
        TaxonomyController,
        CleaningController,
        CurationController,
        DocumentController,
        HierarchyController,
        PublicController,
        SystemController,
        TextQualityController,
        TypologyController,
    ]

    if (spa := curator_spa_router()) is not None:
        route_handlers.append(spa)

    return Litestar(
        route_handlers=route_handlers,
        middleware=[RequestContextMiddleware()],
        dependencies={"unit_of_work": Provide(provide_unit_of_work)},
        exception_handlers={
            DomainException: domain_exception_handler,
            IntegrityError: integrity_error_handler,
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

"""Litestar application factory, importable without the deployable entrypoint."""

from litestar import Litestar
from litestar.di import Provide
from litestar.logging import LoggingConfig
from sqlalchemy.exc import IntegrityError

from memoria_curitibana.api.controllers.cleaning_controller import CleaningController
from memoria_curitibana.api.controllers.document_controller import DocumentController
from memoria_curitibana.api.controllers.hierarchy_controller import HierarchyController
from memoria_curitibana.api.controllers.taxonomy_controller import TaxonomyController
from memoria_curitibana.api.controllers.text_quality_controller import TextQualityController
from memoria_curitibana.api.dependencies import provide_unit_of_work
from memoria_curitibana.api.handlers import domain_exception_handler, integrity_error_handler
from memoria_curitibana.core.config import settings
from memoria_curitibana.core.logger import InterceptHandler, intercept_stdlib_logging
from memoria_curitibana.domains.archive.exceptions import DomainException


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
    return Litestar(
        route_handlers=[
            TaxonomyController,
            CleaningController,
            DocumentController,
            HierarchyController,
            TextQualityController,
        ],
        dependencies={"unit_of_work": Provide(provide_unit_of_work)},
        exception_handlers={
            DomainException: domain_exception_handler,
            IntegrityError: integrity_error_handler,
        },
        logging_config=_logging_config(),
        debug=settings.DEBUG,
    )


app = create_app()

# Uvicorn's own ``dictConfig`` runs after this and does not disable existing loggers,
# so this handler also survives for the records that do not originate from Litestar.
intercept_stdlib_logging()

__all__ = ["app", "create_app"]

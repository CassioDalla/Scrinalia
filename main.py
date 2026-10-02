"""Litestar application entrypoint."""

from litestar import Litestar
from litestar.di import Provide
from litestar.logging import LoggingConfig
from sqlalchemy.exc import IntegrityError

from api.controllers.cleaning_controller import CleaningController
from api.controllers.document_controller import DocumentController
from api.controllers.taxonomy_controller import TaxonomyController
from api.dependencies import provide_unit_of_work
from api.handlers import domain_exception_handler, integrity_error_handler
from core.config import settings
from core.logger import InterceptHandler, intercept_stdlib_logging
from domains.archive.exceptions import DomainException

# Litestar and uvicorn both apply a ``dictConfig`` at startup, which would replace
# the stdlib handlers built by ``core.logger``. Configuring Litestar with only the
# intercept handler keeps the loguru sinks as the single destination, and Litestar's
# default schema warning is surfaced instead of being silently swallowed.
logging_config = LoggingConfig(
    loggers={"litestar": {"level": settings.LOG_LEVEL, "handlers": ["intercept"], "propagate": False}},
    root={"level": settings.LOG_LEVEL, "handlers": ["intercept"]},
    handlers={"intercept": {"class": InterceptHandler}},
    configure_root_logger=True,
    disable_existing_loggers=False,
)

app = Litestar(
    route_handlers=[TaxonomyController, CleaningController, DocumentController],
    dependencies={"unit_of_work": Provide(provide_unit_of_work)},
    exception_handlers={
        DomainException: domain_exception_handler,
        IntegrityError: integrity_error_handler,
    },
    logging_config=logging_config,
    debug=settings.DEBUG,
)

# Uvicorn's own ``dictConfig`` runs after this and does not disable existing loggers,
# so this handler also survives for the records that do not originate from Litestar.
intercept_stdlib_logging()

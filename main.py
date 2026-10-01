# main.py
from litestar import Litestar
from litestar.di import Provide
from sqlalchemy.exc import IntegrityError

from api.controllers.cleaning_controller import CleaningController
from api.controllers.document_controller import DocumentController
from api.controllers.taxonomy_controller import TaxonomyController
from api.handlers import domain_exception_handler, integrity_error_handler, value_error_handler
from core.database import get_db_api
from domains.archive.exceptions import DomainException

app = Litestar(
    route_handlers=[TaxonomyController, CleaningController, DocumentController],
    dependencies={"db_session": Provide(get_db_api)},
    exception_handlers={
        DomainException: domain_exception_handler,
        IntegrityError: integrity_error_handler,
        ValueError: value_error_handler,
    },
    debug=True,
)

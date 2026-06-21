# main.py
from litestar import Litestar
from litestar.di import Provide

from api.controllers.taxonomy_controller import TaxonomyController
from api.handlers import domain_exception_handler
from core.database import get_db_api
from domains.archive.exceptions import DomainException

app = Litestar(
    route_handlers=[TaxonomyController],
    dependencies={"db_session": Provide(get_db_api)},
    exception_handlers={DomainException: domain_exception_handler},
    debug=True,
)

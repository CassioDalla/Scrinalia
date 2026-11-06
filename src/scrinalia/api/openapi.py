"""The API's own identity in the generated contract, declared once.

Litestar ships ``DEFAULT_OPENAPI_CONFIG`` — ``title="Litestar API"``, ``version="1.0.0"`` — and
``create_app()`` never overrode it, so the committed contract carried the framework's strings rather
than this project's. It reads as plausible and is wrong: the served ``info.version`` stayed at the
framework's default through a version bump, and the title named the framework instead of the system.
Measured before this module, with ``pyproject.toml`` at 1.1.0:
``create_app().openapi_config`` was ``OpenAPIConfig(title='Litestar API', version='1.0.0')``.

The version comes from the **installed distribution metadata**, which ``pyproject.toml`` defines once.
``apps/curator/vite.config.ts`` reads that same file for the SPA footer, so the number an archivist
reads at the foot of a page and the number a client reads in ``info.version`` are one fact;
``testing/unit/api/test_openapi_metadata.py`` pins them together and fails if a release moves one and
not the other. The helper itself lives in ``core.version`` because the open dataset's manifest also
reports the software version (ADR 0024), and a domain worker must not import this module.
"""

from litestar.openapi.config import OpenAPIConfig

from scrinalia.core.version import DISTRIBUTION, application_version

#: What the contract calls the system. Not the framework: a consumer reading the document is
#: integrating with Scrinalia, and ``Litestar`` is the detail of how it is served.
TITLE = "Scrinalia API"

__all__ = ["DISTRIBUTION", "TITLE", "application_version", "openapi_config"]


def openapi_config() -> OpenAPIConfig:
    """A fresh configuration for each app.

    Built per call and not shared: Litestar keeps the schema registry and the accumulated components
    on the config it is handed, so two applications sharing one instance would share what one of them
    generated.
    """
    return OpenAPIConfig(title=TITLE, version=application_version())

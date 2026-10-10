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
not the other.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

from litestar.openapi.config import OpenAPIConfig

#: The distribution whose metadata owns the version — the ``[project] name`` of ``pyproject.toml``.
DISTRIBUTION = "scrinalia"

#: What the contract calls the system. Not the framework: a consumer reading the document is
#: integrating with Scrinalia, and ``Litestar`` is the detail of how it is served.
TITLE = "Scrinalia API"


def application_version() -> str:
    """The installed distribution's version.

    The failure is explicit on purpose. An environment that imported the package without installing
    it has no version to report, and a contract that quietly fell back to ``"0.0.0"`` would be a
    document claiming a release that does not exist — the same defect this module removes.
    """
    try:
        return distribution_version(DISTRIBUTION)
    except PackageNotFoundError as error:  # pragma: no cover - the project is always installed
        raise RuntimeError(
            f"the distribution '{DISTRIBUTION}' is not installed, so the contract has no version: "
            "run `uv sync --locked` and generate it through `uv run`."
        ) from error


def openapi_config() -> OpenAPIConfig:
    """A fresh configuration for each app.

    Built per call and not shared: Litestar keeps the schema registry and the accumulated components
    on the config it is handed, so two applications sharing one instance would share what one of them
    generated.
    """
    return OpenAPIConfig(title=TITLE, version=application_version())

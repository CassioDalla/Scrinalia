"""The installed distribution's version, one fact shared by the API contract and the dataset.

It lives in ``core`` and not in ``api/openapi.py`` because the open dataset (ADR 0024) writes the
software version into ``manifest.json``, and a domain worker importing the API layer would invert the
dependency. The API module re-exports it for the contract it builds; the version itself is defined
once, by ``pyproject.toml``, and read from the installed distribution metadata.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

#: The distribution whose metadata owns the version — the ``[project] name`` of ``pyproject.toml``.
DISTRIBUTION = "scrinalia"


def application_version() -> str:
    """
    The installed distribution's version.

    The failure is explicit on purpose. An environment that imported the package without installing
    it has no version to report, and a contract that quietly fell back to ``"0.0.0"`` would be a
    document claiming a release that does not exist.
    """
    try:
        return distribution_version(DISTRIBUTION)
    except PackageNotFoundError as error:  # pragma: no cover - the project is always installed
        raise RuntimeError(
            f"the distribution '{DISTRIBUTION}' is not installed, so the contract has no version: "
            "run `uv sync --locked` and generate it through `uv run`."
        ) from error

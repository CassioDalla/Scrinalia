"""The contract's ``info`` block is the project's, not the framework's.

Litestar's ``DEFAULT_OPENAPI_CONFIG`` is ``title="Litestar API"``, ``version="1.0.0"``. An
``openapi_config=`` that is never passed means the committed contract describes the framework and
pins a version nobody bumps, so ``info.version`` is a number a client reads and the project does not
own. The three tests below close the three ways that can drift: the title, the environment, and the
committed file.
"""

from __future__ import annotations

import json
import tomllib
from importlib.metadata import version as distribution_version
from pathlib import Path

from litestar.openapi.config import OpenAPIConfig

from scrinalia.api.openapi import DISTRIBUTION, TITLE
from scrinalia.asgi import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CONTRACT = REPO_ROOT / "packages" / "api-contract" / "openapi.json"


def _config() -> OpenAPIConfig:
    config = create_app().openapi_config
    assert config is not None, "the app was built without an OpenAPI configuration"
    return config


def _pyproject_version() -> str:
    """The version ``pyproject.toml`` declares — the one definition the rest is derived from."""
    manifest = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return str(manifest["project"]["version"])


def test_the_contract_names_the_system_and_not_the_framework() -> None:
    assert _config().title == TITLE


def test_the_contract_version_is_the_installed_distributions() -> None:
    """The served document reports the distribution, which is where the version is installed from."""
    assert _config().version == distribution_version(DISTRIBUTION)


def test_the_installed_distribution_matches_pyproject() -> None:
    """The environment and the source agree.

    ``uv sync --locked`` is what keeps them in step, and this fails when a version bump landed in
    ``pyproject.toml`` without the environment following it — the state in which a machine generates
    a contract for a release it is not running.
    """
    assert distribution_version(DISTRIBUTION) == _pyproject_version()


def test_the_committed_contract_carries_the_projects_version() -> None:
    """The file CI compares against, read on its own terms.

    CI already diffs a fresh dump against this file; this says *what* it must contain, so a stale
    contract names the number it is stale about instead of only reporting that the two differ.
    """
    info = json.loads(CONTRACT.read_text(encoding="utf-8"))["info"]
    assert info["title"] == TITLE
    assert info["version"] == _pyproject_version()

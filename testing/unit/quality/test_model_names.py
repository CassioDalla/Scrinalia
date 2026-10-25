"""No two schema models share a name (issue #184).

Two pydantic models named ``HierarchyMaterialisationRequest`` lived in two packages — the HTTP body
and the service command — and the contract pointed at one while an editor opening the domain package
found the other. The collision cost a real mistake before it was named: a sweep keyed on "the model
of this body" resolved the wrong class in one package and missed the other, and only a later gate saw
it.

The name is the whole check. A class name that exists twice across the packages that name things in
the contract, in the API and in the domain's commands sends a reader to whichever file their editor
finds first — and the two drift, which is what the duplicated docstrings already showed.
"""

from __future__ import annotations

import collections
import importlib
import pathlib

from pydantic import BaseModel

#: The packages whose classes name a model of the contract, of the API or of a domain command.
SCHEMA_PACKAGES = (
    "scrinalia.api.schemas",
    "scrinalia.domains.archive.schemas",
    "scrinalia.domains.identity.schemas",
)


def models_by_name() -> dict[str, list[str]]:
    """Every pydantic model the schema packages **define**, grouped by class name."""
    found: collections.defaultdict[str, list[str]] = collections.defaultdict(list)
    for package in SCHEMA_PACKAGES:
        module = importlib.import_module(package)
        for path in sorted(pathlib.Path(module.__path__[0]).glob("*.py")):
            if path.name == "__init__.py":
                continue
            submodule = importlib.import_module(f"{package}.{path.stem}")
            for name, obj in vars(submodule).items():
                if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == submodule.__name__:
                    found[name].append(submodule.__name__)
    return dict(found)


def test_the_walk_finds_the_schema_models() -> None:
    """The gate guards itself: a walk that stopped importing the modules would pass for the wrong reason."""
    assert len(models_by_name()) >= 250, f"the walk found {len(models_by_name())} models; it used to find 276"


def test_no_two_schema_models_share_a_name() -> None:
    duplicated = {name: modules for name, modules in models_by_name().items() if len(modules) > 1}

    assert not duplicated, (
        f"these class names exist twice: {sorted(duplicated.items())}. The contract and the commands "
        "would send a reader to whichever file their editor finds first — give the second one its own "
        "name, and a domain input is a `*Command` (`CreateHierarchyNodeCommand` already is)."
    )

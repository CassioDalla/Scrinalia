"""Every request body refuses a field the route does not know (issue #177).

The body position is loud only where a model happens to say so. Measured before this change, against
the 53 request bodies the contract carried: **22** declared ``extra="forbid"`` and **31** kept
pydantic's default, so an unknown field — or an optional field renamed — answered **200** on one
route and **400** on the next. A stale client could not tell which kind of route it was talking to,
and the same typo was a silent no-op or an error depending on the model it hit.

The policy is one base, :class:`scrinalia.core.schemas.RequestModel`, and these two tests keep it
that way: the first resolves the bodies from the **built application** — a hand list would be the
second definition this issue removes — and the second refuses a model that stops inheriting it.
"""

from __future__ import annotations

import inspect
import typing

from litestar.testing import TestClient
from pydantic import BaseModel

from scrinalia.asgi import create_app


def request_body_models() -> dict[str, type[BaseModel]]:
    """Every model a handler annotates as a parameter, resolved from the assembled router."""
    app = create_app()
    found: dict[str, type[BaseModel]] = {}
    with TestClient(app=app):
        for route in app.routes:
            for handler in getattr(route, "route_handlers", []) or []:
                function = getattr(handler, "fn", None)
                if function is None:
                    continue
                # The router wraps a sync handler in ``AsyncCallable``, and the annotations live on
                # the callable it wraps; ``get_type_hints`` also strips the ``Annotated`` a
                # dependency parameter carries.
                function = getattr(function, "func", function)
                hints: dict[str, object] = {}
                if inspect.isroutine(function):
                    try:
                        hints = typing.get_type_hints(function, include_extras=False)
                    except NameError:
                        # The framework's own options handler annotates ``scope`` with a type its
                        # module does not import; the raw annotations are enough for a parameter
                        # that is not a body.
                        hints = {}
                for parameter in inspect.signature(function).parameters.values():
                    annotation = hints.get(parameter.name, parameter.annotation)
                    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                        found[f"{annotation.__module__}.{annotation.__qualname__}"] = annotation
    return found


def contract_body_names() -> set[str]:
    """The schema names the contract points at from a ``requestBody`` — the other side of the walk."""
    schema = create_app().openapi_schema.to_schema()
    names: set[str] = set()
    for operations in schema["paths"].values():
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            reference = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("$ref")
            )
            if reference:
                names.add(reference.rsplit("/", 1)[-1])
    return names


def test_the_walk_finds_every_body_the_contract_declares() -> None:
    """The gate guards itself: a walk that stopped finding bodies would pass for the wrong reason."""
    walked = {model.__name__ for model in request_body_models().values()}
    declared = contract_body_names()

    assert declared - walked == set(), (
        f"the contract declares bodies the walk did not resolve: {sorted(declared - walked)}. The "
        "gate would be blind to them."
    )
    assert walked == declared, f"the walk resolved bodies the contract does not carry: {sorted(walked - declared)}"


def test_every_request_body_refuses_an_unknown_field() -> None:
    """One policy: a field the route does not know is a 400, not a silent drop."""
    offenders = {
        name: model.model_config.get("extra")
        for name, model in request_body_models().items()
        if model.model_config.get("extra") != "forbid"
    }

    assert not offenders, (
        "these request bodies accept an unknown field and drop it: "
        f"{sorted(offenders)}. Inherit `scrinalia.core.schemas.RequestModel` instead of `BaseModel`, "
        "so a stale client fails loudly instead of having an optional field ignored (#177)."
    )

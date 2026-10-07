"""
The generated contract must not depend on the hash seed.

Litestar builds the schema for a field by fetching the **shared component** of the type it references
and then applying the field's own kwargs to it::

    schema = self.schema_registry.get_schema_for_field_definition(field_definition)
    self.process_schema_result(field_definition, schema)
    if schema.description is None:
        schema.description = field_definition.annotation.__doc__

So a ``Field(description=...)`` on a field typed with a shared enum does not document *that field* —
it writes the description into the enum's component for the whole document. Whichever field is walked
first wins, and that order depends on ``PYTHONHASHSEED``: measured before the fix, seeds 0 and 7 gave
the Portuguese field description while the others gave the enum's docstring, so ``bun run contract``
emitted two different files from identical code and CI's "the committed contract is current" check
failed at random.

The two tests below pin it from both ends: the structural one catches the **cause** in any process,
and the one on the served document catches the **symptom** on the seed this process happened to draw.
"""

import typing
from collections.abc import Iterator

import pytest
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from scrinalia.asgi import create_app
from scrinalia.domains.archive.models.enums import (
    ArchiveReviewStatus,
    StopwordsScope,
    WorkerRunStatus,
)

#: The enum types that reach the contract as a component. ``AnomalyType`` and ``AnomalyReason`` are
#: deliberately absent: nothing in the API exposes them, so there is no component to leak into.
SHARED_COMPONENT_TYPES: tuple[type, ...] = (
    StopwordsScope,
    ArchiveReviewStatus,
    WorkerRunStatus,
)


def _component_names() -> set[str]:
    """The schema names the served contract actually carries."""
    schema = create_app().openapi_schema.to_schema()
    return set(schema.get("components", {}).get("schemas", {}))


def _all_models() -> Iterator[type[BaseModel]]:
    """Every pydantic model reachable from the app, without importing each schema module by hand."""
    seen: set[type[BaseModel]] = set()
    pending = [BaseModel]
    while pending:
        for subclass in pending.pop().__subclasses__():
            if subclass in seen:
                continue
            seen.add(subclass)
            pending.append(subclass)
            yield subclass


def _references_shared_type(annotation: object) -> bool:
    """Whether the annotation is one of the shared types, directly or inside a union/list."""
    if annotation in SHARED_COMPONENT_TYPES:
        return True
    return any(_references_shared_type(argument) for argument in typing.get_args(annotation))


def test_no_field_description_leaks_into_a_shared_type() -> None:
    """
    A field of a **contract component** that references a shared enum must not carry a description.

    Adding one does not document the field: it becomes the enum's description in the contract, for
    every consumer, and which field wins is decided by the hash seed. Document the type instead — the
    enum's docstring reaches the contract and every field referencing it inherits it.

    Scoped to the models that are components on purpose. An internal DTO that never reaches the
    contract cannot leak into it, and forbidding a useful description on ``DocumentSearchQuery`` would
    trade real documentation for a bug that cannot happen — until the DTO becomes a component, at
    which point this test starts covering it. (The two domain *commands* that were the twins of the
    fixed request models were cleaned anyway: same mistake, and leaving one loaded invites the bug
    back.)
    """
    components = _component_names()
    offenders: list[str] = []

    for model in _all_models():
        if model.__name__ not in components:
            continue
        for name, field in model.model_fields.items():
            if not isinstance(field, FieldInfo) or field.description is None:
                continue
            if _references_shared_type(field.annotation):
                offenders.append(f"{model.__module__}.{model.__qualname__}.{name}")

    assert not offenders, (
        f"Campos com descrição própria sobre um tipo compartilhado: {sorted(offenders)}. A descrição "
        "do campo vira a descrição do componente no contrato, e qual campo vence depende do "
        "PYTHONHASHSEED — documente o tipo, não o campo."
    )


@pytest.mark.parametrize("enum_type", SHARED_COMPONENT_TYPES)
def test_a_shared_type_documents_itself(enum_type: type) -> None:
    """
    Each shared type has a docstring, because that is what the contract will show.

    Without one the component would be undocumented — which is what made a field description look
    like an improvement in the first place.
    """
    assert enum_type.__doc__, f"{enum_type.__name__} não tem docstring: o contrato sairia sem descrição"


def test_every_enum_component_description_is_the_types_own() -> None:
    """
    End to end, on the document the API serves: no enum component carries a foreign text.

    This is the assertion that would have failed on the seeds that flipped; the structural test above
    is what makes it reliable, since it catches the cause whatever seed this process drew.
    """
    components = create_app().openapi_schema.to_schema().get("components", {}).get("schemas", {})

    for enum_type in SHARED_COMPONENT_TYPES:
        component = components.get(enum_type.__name__)
        assert component is not None, f"{enum_type.__name__} não está no contrato"
        assert component.get("description") == enum_type.__doc__, (
            f"A descrição de {enum_type.__name__} no contrato não é a do próprio tipo — algum campo "
            "escreveu a dele por cima."
        )

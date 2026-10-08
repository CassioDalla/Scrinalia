"""Requests of the collection vocabulary catalogue: the terms this archive declares."""

from pydantic import BaseModel, ConfigDict, Field

from scrinalia.domains.archive.models.enums import CollectionTermKind


class ArrangementTermCreateRequest(BaseModel):
    """Registers a rung name the hierarchy proposal will suggest for a code token."""

    token: str = Field(
        min_length=1,
        max_length=100,
        description="Token do código de referência (ex.: 'BETA'), ou o código inteiro (ex.: 'ACERVO RAIZ').",
    )
    display_name: str = Field(min_length=1, max_length=200, description="O nome que o arquivista lê na proposta.")


class ArrangementTermUpdateRequest(BaseModel):
    """
    Partial update of an arrangement term.

    There is no delete: a removed suggestion would simply come back on the next proposal, and the
    archivist would have no way to tell that from the software forgetting. ``is_active=false``
    retires the name and keeps the row.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")


class CollectionTermCreateRequest(BaseModel):
    """Registers a term the collection carries that is not a subject."""

    term: str = Field(min_length=1, max_length=200, description="A grafia como ela aparece no acervo.")
    kind: CollectionTermKind


class CollectionTermUpdateRequest(BaseModel):
    """
    Partial update of a collection term.

    Renaming and re-kinding are allowed because the term is a statement about the collection, not a
    key other rows point at; the pair ``(term, kind)`` is unique, so a collision is a named conflict.
    """

    term: str | None = Field(default=None, min_length=1, max_length=200)
    kind: CollectionTermKind | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")

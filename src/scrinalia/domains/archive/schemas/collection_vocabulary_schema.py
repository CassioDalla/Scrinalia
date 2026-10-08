"""
The collection vocabulary catalogue: what the guard reads and the curator edits.

Two catalogues live in one module because they are one screen and one idea — the terms the
*collection* declares, as opposed to the terms the *language* does. The arrangement vocabulary
names the rungs of the hierarchy proposal; the collection terms say which toponyms are places and
which names are people.
"""

from pydantic import BaseModel, ConfigDict, Field

from scrinalia.domains.archive.models.enums import CollectionTermKind


class ArrangementTermDTO(BaseModel):
    """One arrangement token and the name the proposal suggests for the rung that carries it."""

    term_id: int
    token: str
    display_name: str
    is_active: bool


class CollectionTermDTO(BaseModel):
    """One non-subject term of the collection, its kind, and the weight of its spelling."""

    term_id: int
    term: str
    kind: CollectionTermKind
    is_active: bool
    #: How many tags carry exactly this spelling. Derived on read, never stored: the guard matches
    #: by name, so the count is the weight at stake when the term is retired.
    tag_count: int = 0


class CreateArrangementTermCommand(BaseModel):
    token: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)


class UpdateArrangementTermCommand(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class CreateCollectionTermCommand(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    kind: CollectionTermKind


class UpdateCollectionTermCommand(BaseModel):
    term: str | None = Field(default=None, min_length=1, max_length=200)
    kind: CollectionTermKind | None = None
    is_active: bool | None = None


class CollectionVocabularyResponse(BaseModel):
    """Both catalogues in one read: the configuration screen shows them together."""

    arrangement_terms: list[ArrangementTermDTO]
    collection_terms: list[CollectionTermDTO]
    #: The kinds the catalogue accepts, so the screen renders a select from the definition instead
    #: of a list of strings that could drift from the enum.
    kinds: list[CollectionTermKind]

    model_config = ConfigDict(extra="forbid")

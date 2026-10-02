from typing import Literal

from pydantic import BaseModel, Field

from memoria_curitibana.domains.archive.schemas.types import SynonymName


class SynonymCommand(BaseModel):
    """
    Write command for creating a synonym link.

    Replaces the untyped ``list[dict]`` previously passed to
    ``create_synonyms``. Exactly one of the canonical targets is set, mirroring the
    ``chk_exclusive_synonym_target`` database constraint.
    """

    synonym_name: SynonymName = Field(description="Raw synonym spelling; stored normalized to lowercase.")
    category: Literal["TAG", "ORG", "LOC", "PER"]
    canonical_tag_id: int | None = None
    canonical_entity_id: int | None = None


class MergeTagsCommand(BaseModel):
    """Command to merge tags into a canonical one."""

    canonical_id: int
    ids_to_merge: list[int]


class MergeEntityCommand(BaseModel):
    """Command to merge entities into a canonical one, optionally renaming it."""

    canonical_id: int
    ids_to_merge: list[int]
    new_name: str | None = None


class ResolveConflictCommand(BaseModel):
    """Command to resolve a Tag/Entity naming collision."""

    winner: Literal["TAG", "ENTITY"]
    tag_id: int
    entity_id: int


class DocumentReviewCommand(BaseModel):
    """Command carrying the archivist's manual edits for one document."""

    description_id: str
    final_title: str | None = None
    scope_content: str | None = None
    archivist_notes: str | None = None


class TagLinkCommand(BaseModel):
    """Command linking one document to one tag."""

    description_id: str
    tag_id: int


class EntityLinkCommand(BaseModel):
    """Command linking one document to one entity."""

    description_id: str
    entity_id: int

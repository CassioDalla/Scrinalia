from datetime import date
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
    changed_by: str | None = Field(default=None, description="Who merged; free text until authentication exists.")


class MergeEntityCommand(BaseModel):
    """Command to merge entities into a canonical one, optionally renaming it."""

    canonical_id: int
    ids_to_merge: list[int]
    new_name: str | None = None


class ResolveConflictCommand(BaseModel):
    """
    Command to resolve a Tag/Entity naming collision.

    ``decided_by`` and ``note`` travel with the verdict because the resolution now leaves a durable
    row: the ledger has to say who decided and why, not only what changed.
    """

    winner: Literal["TAG", "ENTITY"]
    tag_id: int
    entity_id: int
    decided_by: str | None = None
    note: str | None = None


class DocumentReviewCommand(BaseModel):
    """
    Command carrying the archivist's manual edits for one document.

    The archivist fixes the whole record, not only the title: every ISAD(G) field the
    Archive layer stores is editable here, and ``changed_by`` answers "who" until
    authentication exists (phase 4). Fields left unset are untouched, so the command is a
    partial patch and the audit trail records only what really changed.
    """

    description_id: str

    # Descriptive identity
    original_title: str | None = None
    final_title: str | None = None
    document_date: date | None = None

    # ISAD(G)
    reference_code: str | None = None
    #: The level is a foreign key now: the text of 3,608 descriptions was migrated into the
    #: catalogue and the free-text column was dropped. The client sends the rung it chose.
    level_id: int | None = None
    #: Diplomatic form of the record, also a foreign key into its own catalogue. The classifier is
    #: its usual author; the archivist is the one who can overrule it, which is why it travels here
    #: rather than staying a machine-only column.
    typology_id: int | None = None
    producers: str | None = None
    admin_bio_history: str | None = None
    admin_archival_history: str | None = None
    provenance: str | None = None
    scope_content: str | None = None
    language_name: str | None = None
    archivist_notes: str | None = None
    #: ISAD(G) 4.1. Carried here since the transfer stopped dropping it; the archivist is the one
    #: who can state a restriction the origin never declared.
    access_conditions: str | None = None

    # Diffusion (Fase 4). Not part of ISAD(G): the institution's decision about what to expose.
    # It travels in the same command because it is edited from the same screen, but it is the
    # only field here that does not describe the record itself.
    is_published: bool | None = None

    # Authorship and note of the review itself
    changed_by: str | None = Field(default=None, description="Who reviewed; free text until authentication exists.")
    review_note: str | None = Field(default=None, description="Why the edit was made; stored in the audit trail.")


class TagLinkCommand(BaseModel):
    """Command linking one document to one tag."""

    description_id: str
    tag_id: int


class EntityLinkCommand(BaseModel):
    """Command linking one document to one entity."""

    description_id: str
    entity_id: int


class CreateMacroCategoryCommand(BaseModel):
    """Command creating an official macro category from a curated cluster."""

    name: str = Field(min_length=1, max_length=100, description="Official name of the semantic drawer.")
    description: str | None = Field(default=None, description="Curator-facing documentation; never sent to the model.")
    classifier_label: str | None = Field(
        default=None,
        description="The proposition the NLI model reads, e.g. 'um assunto sobre obras e construção'. "
        "When omitted the bare name is used.",
    )


class UpdateMacroCategoryCommand(BaseModel):
    """Partial update of a macro category and its activation state."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    classifier_label: str | None = None
    is_active: bool | None = None

from typing import Literal

from pydantic import Field, model_validator

from scrinalia.core.schemas import RequestModel
from scrinalia.domains.archive.models.enums import StopwordMatch, StopwordsScope
from scrinalia.domains.archive.schemas.entity_schema import (
    ConflictBatchResult,
    ConflictPairKind,
    ConflictResolutionData,
    ConflictWinner,
    EntityKind,
)
from scrinalia.domains.archive.schemas.responses import RouteResponse


class MergeRequest(RequestModel):
    canonical_id: int
    ids_to_merge: list[int] = Field(min_length=1, description="List of IDs that will be merged and deleted.")
    new_name: str | None = None


class EntityMergeRequest(RequestModel):
    """
    The verdict on a cluster of entities, with its authorship.

    ``note`` is not decoration: the merge now leaves a durable ledger row per absorbed entity, and
    a row that cannot say why the decision was taken is a poorer audit trail. It is a separate
    schema from ``MergeRequest`` (the tags') because only this route records the note.
    """

    canonical_id: int
    ids_to_merge: list[int] = Field(min_length=1, description="List of IDs that will be merged and deleted.")
    new_name: str | None = Field(
        default=None, description="Optional new name for the canonical; the old one becomes a synonym."
    )
    note: str | None = Field(default=None, description="Why; kept in the merge ledger.")


class EntityMergePreviewRequest(RequestModel):
    """Dry-run of an entity merge. Read-only: the plan, computed by the same planner the write uses."""

    canonical_id: int
    ids_to_merge: list[int] = Field(min_length=1)
    new_name: str | None = None


class MergeBatchRequest(RequestModel):
    """Applies a set of proposals. Including a pending one is the archivist's decision."""

    proposal_ids: list[int] = Field(min_length=1, description="Proposals to apply, in order.")
    note: str | None = Field(default=None, description="Why; kept for auditing.")


class MergeSuggestionRequest(RequestModel):
    """Parameters of a suggestion run over the tag catalog."""

    threshold: float = Field(default=0.65, gt=0, le=1, description="pg_trgm similarity floor.")
    limit: int = Field(default=50, ge=1, le=500, description="How many clusters the run may register.")


class MergeProposalDecisionRequest(RequestModel):
    """The archivist's verdict on one proposed cluster. It records intent; it does not merge."""

    status: Literal["APPROVED", "REJECTED"]
    note: str | None = Field(default=None, description="Why; kept for auditing.")


class MergePreviewRequest(RequestModel):
    """Dry-run of a merge, by persisted proposal or by an explicit canonical + ids."""

    proposal_id: int | None = None
    canonical_id: int | None = None
    ids_to_merge: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_source_of_truth(self) -> "MergePreviewRequest":
        if self.proposal_id is None and (self.canonical_id is None or not self.ids_to_merge):
            raise ValueError("informe 'proposal_id' ou 'canonical_id' com 'ids_to_merge'")
        if self.proposal_id is not None and (self.canonical_id is not None or self.ids_to_merge):
            raise ValueError("'proposal_id' não pode ser combinado com 'canonical_id'/'ids_to_merge'")
        return self


class StopwordCreateRequest(RequestModel):
    """Terms to ban from one axis. ``TAG`` by default: the axis this catalog governs."""

    words: list[str] = Field(min_length=1, description="Termos a banir (normalizados ao gravar).")
    # No ``description`` here on purpose: Litestar writes a field's description into the shared
    # schema of the type it references, so a description on this field becomes the description of
    # ``StopwordsScope`` for the whole contract — and which field is walked first depends on the
    # hash seed. The axis is documented once, on the enum, and every field inherits it.
    scope: StopwordsScope = Field(default=StopwordsScope.TAG)
    #: How the ban matches an extracted name. ``TOKEN`` also blocks the names that contain the word;
    #: ``EXACT`` blocks the spelling alone (#160). Only the ENTITY/ALL axes read it.
    match_mode: StopwordMatch = Field(default=StopwordMatch.TOKEN)


class StopwordRemovalRequest(RequestModel):
    """Terms to un-ban. With no scope, the word leaves every axis it was banned from."""

    words: list[str] = Field(min_length=1)
    scope: StopwordsScope | None = Field(default=None)


class StopwordMatchRequest(RequestModel):
    """Changes how the given banned terms match, leaving their axis, origin and existence alone."""

    words: list[str] = Field(min_length=1)
    match_mode: StopwordMatch


class StopwordsRequest(RequestModel):
    words: list[str] = Field(
        default_factory=list,
        description="Words to register before purging; omit to purge with the list already stored.",
    )


class SuggestMacroRequest(RequestModel):
    source_type: Literal["tags", "documents"] = Field(
        default="tags", description="The data source the AI will use to generate the clusters."
    )
    columns_to_extract: list[str] | None = Field(
        default=None,
        min_length=1,
        description=(
            "The AI text columns the clustering reads. Omitted means the code default, published by "
            "``GET /taxonomy/tags/suggest-macro/columns``; it only applies with source_type='documents'."
        ),
    )

    @model_validator(mode="after")
    def _columns_only_for_documents(self) -> "SuggestMacroRequest":
        """Refuse a list the clustering would ignore, instead of accepting it in silence (#174)."""
        if self.source_type == "tags" and self.columns_to_extract is not None:
            raise ValueError("columns_to_extract só vale com source_type='documents'.")
        return self


class MacroCategoryCreateRequest(RequestModel):
    """Official macro category the curator creates from a suggested cluster."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, description="Curator-facing documentation. Never sent to the model.")
    classifier_label: str | None = Field(
        default=None,
        description="The proposition the NLI model reads. Omitted means the bare name is used.",
    )


class MacroCategoryUpdateRequest(RequestModel):
    """Partial edit of a macro category."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    classifier_label: str | None = None
    is_active: bool | None = None


class ReclassifyEntityRequest(RequestModel):
    new_type: Literal["ORG", "PER", "LOC"]


class EntityRenameRequest(RequestModel):
    """
    A new spelling for one name, and whether the old one keeps resolving to it.

    ``keep_old_synonym`` defaults to true because that is what the merge does and what the extractor
    needs: the old spelling stays anchored, so a description extracted tomorrow under it still resolves
    to this entity. Turning it off is the honest answer to a typo — ``Prefeitura Muinicipal`` is not a
    spelling anybody should keep — and it is offered rather than assumed because only the archivist
    knows which of the two an edit is.
    """

    new_name: str = Field(min_length=1, max_length=255, description="The spelling the catalogue will show.")
    keep_old_synonym: bool = Field(
        default=True, description="Whether the previous spelling keeps resolving to this entity."
    )
    note: str | None = Field(default=None, description="Why; kept in the merge ledger, with the undo.")


class TagCurationRequest(RequestModel):
    """
    The archivist's verdict on which drawer one tag belongs to.

    ``macro_category_id`` is required and nullable: ``null`` means "this tag is not a subject", a
    decision, and not "no decision was sent". A default would blur the two, and telling them apart
    is the whole reason the command exists.
    """

    macro_category_id: int | None = Field(
        description="Drawer the tag moves into; ``null`` takes it out of the subject axis."
    )
    note: str | None = Field(default=None, description="Why; kept in the tag's ledger.")


class NerExclusionRequest(RequestModel):
    """Terms a curator declares to belong to the subject axis, not to named entities."""

    words: list[str] = Field(min_length=1, description="Terms to keep out of the NER extraction.")
    reason: str | None = Field(default=None, description="Why the decision was made; kept for auditing.")


class NerExclusionRemovalRequest(RequestModel):
    """
    Undoes the ban for the given terms.

    Deliberately **not** ``NerExclusionRequest``: removing a ban has no provenance to declare — the
    deletion is its own record — and sharing the model advertised a ``reason`` the route ignores,
    which the generated client offered to every caller (issue #176).
    """

    words: list[str] = Field(min_length=1, description="Terms to put back into the NER extraction.")


class SubjectExclusionPreviewRequest(RequestModel):
    """
    The terms the dry run would act on, and nothing else.

    Deliberately **not** ``SubjectExclusionRequest``: a plan reads the terms, while a ``reason``
    describes the decision the *write* records and ``source`` says where the verdict came from — a
    preview can know neither. Declaring the write's model advertised both to every caller of the
    dry run (issue #175).
    """

    words: list[str] = Field(min_length=1, description="Terms the write would record, or refuse.")


class SubjectExclusionRequest(RequestModel):
    """
    Terms a curator declares to be no subject at all (the second half of NENHUMA).

    ``source`` says where the verdict came from: ``HUMAN`` for a term the archivist typed, ``RULE``
    for one the deterministic guard had already refused and the archivist confirmed. The column
    existed since the table was created and nothing ever wrote ``RULE``; the suggestion route is what
    makes the distinction real, and it is what lets a later reader tell a judgement from a shape.
    """

    words: list[str] = Field(min_length=1, description="Terms to keep out of the subject classifier.")
    reason: str | None = Field(default=None, description="Why the decision was made; kept for auditing.")
    source: Literal["HUMAN", "RULE"] = Field(
        default="HUMAN",
        description="HUMAN: o arquivista digitou o termo. RULE: veio do guarda determinístico e foi confirmado.",
    )


class SubjectExclusionRemovalRequest(RequestModel):
    """
    Undoes the decision for the given terms.

    Deliberately **not** ``SubjectExclusionRequest``: removing an exclusion has no provenance to
    declare — the deletion is its own record — and sharing the model forced a ``source`` the route
    ignores, which the generated client would then require of every caller.
    """

    words: list[str] = Field(min_length=1, description="Terms to put back into the subject classifier.")


class ConflictResolutionResponse(RouteResponse):
    data: ConflictResolutionData


class ConflictPreviewRequest(RequestModel):
    """
    The pair whose impact is being asked about.

    No winner: the preview returns **both** verdicts, because "which one should win?" is a question
    about the difference between them, and asking one side at a time would need two round trips to
    answer it.
    """

    tag_id: int = Field(description="Id da tag no vocabulário.")
    entity_id: int = Field(description="Id da entidade nomeada.")


class ConflictResolutionRequest(RequestModel):
    """
    The verdict, with its authorship.

    ``decided_by`` and ``note`` are not decoration: the resolution now leaves a durable ledger row,
    and a row that cannot say who decided is not an audit trail.
    """

    winner: ConflictWinner
    tag_id: int
    entity_id: int
    note: str | None = Field(default=None, description="Por que decidiu; fica no ledger da resolução.")


class ConflictBatchRequest(RequestModel):
    """
    One verdict for a whole **selection** of collisions, not for a pair.

    The selection is the structural population the batch is meaningful for (``pair_kind``: the same
    spelling on both axes) narrowed by category (``entity_type``: "a street is an entity" is a
    decision about a set). ``limit`` bounds one request — the write is undoable pair by pair, but a
    click that writes thousands of ledger rows is a click nobody reviewed.
    """

    winner: ConflictWinner
    pair_kind: ConflictPairKind = "exact_name"
    entity_type: EntityKind | None = None
    threshold: float = Field(default=0.85, gt=0, le=1, description="pg_trgm similarity floor.")
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Quantos pares uma requisição pode escrever; o restante continua na seleção.",
    )
    note: str | None = Field(default=None, description="Por que decidiu; fica no ledger de cada resolução.")


class ConflictBatchResponse(RouteResponse):
    data: ConflictBatchResult

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memoria_curitibana.domains.archive.schemas.types import TagName


class TagRelevanceCount(BaseModel):
    name: str
    total_usage: int

    model_config = ConfigDict(from_attributes=True)


class TagRelevanceIdf(BaseModel):
    name: str
    frequency: float
    weight_idf: float
    score_tfidf: float

    model_config = ConfigDict(from_attributes=True)


class TagRelevanceResponse(BaseModel):
    mode: Literal["count", "tfidf"]
    payload: list[TagRelevanceCount | TagRelevanceIdf]

    @classmethod
    def from_payload(cls, payload: list[TagRelevanceCount | TagRelevanceIdf]) -> "TagRelevanceResponse":
        if not payload:
            return cls(mode="count", payload=[])

        first_item = payload[0]

        if isinstance(first_item, TagRelevanceCount):
            return cls(mode="count", payload=payload)

        elif isinstance(first_item, TagRelevanceIdf):
            return cls(mode="tfidf", payload=payload)

        raise ValueError("Tipo de payload desconhecido")


class TagSimilarity(BaseModel):
    tag_id: int
    name: str
    similarity: float

    model_config = ConfigDict(from_attributes=True)


# Think about a way to merge this with the schema above
class TagPairSimilarity(BaseModel):
    id_1: int
    name_1: str
    id_2: int
    name_2: str
    sim_score: float

    model_config = ConfigDict(from_attributes=True)


class TagCount(BaseModel):
    """A tag and how many documents link to it (used by the merge suggestions)."""

    tag_id: int
    name: str
    document_count: int = 0
    # The curator needs to know whether a merge would drop a classification, so the catalog
    # read carries the tag's own macro category and confidence score.
    macro_category_id: int | None = None
    ai_confidence_score: float | None = None

    model_config = ConfigDict(from_attributes=True)


class TagMergeMember(BaseModel):
    """One tag inside a proposed merge cluster."""

    tag_id: int
    name: str
    document_count: int


class TagMergeSuggestion(BaseModel):
    """
    A group of tags that probably mean the same thing.

    Suggestion only: the archivist approves it through ``/tags/merge``. ``reason`` records
    how the group was formed (``TRIGRAM`` for spelling closeness, ``PLURAL`` for
    singular/plural, ``MIXED`` for both), so the evidence travels with the proposal.
    """

    canonical_id: int
    canonical_name: str
    total_documents: int
    reason: str
    members: list[TagMergeMember]


class MergeResponse(BaseModel):
    documents_updated: int
    tags_deleted: int
    # Ledger rows written by this merge: the handles a client needs to undo it.
    merge_ids: list[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# TAG MERGE PROPOSALS (curation flow)
# ==========================================


class TagMergeProposalDTO(BaseModel):
    """
    A persisted cluster proposal plus the human decision about it.

    The evidence (``members``, ``total_documents``, ``review_flags``) is refreshed by every
    suggestion run; the decision (``status``, ``decided_by``, ``decided_at``) is written only
    by a human and is never overwritten by the routine.
    """

    proposal_id: int
    fingerprint: str
    canonical_id: int | None = None
    canonical_name: str
    reason: str
    total_documents: int
    review_flags: list[str] = Field(default_factory=list)
    members: list[TagMergeMember] = Field(default_factory=list)
    status: Literal["SUGGESTED", "APPROVED", "REJECTED"]
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TagMergeProposalListResponse(BaseModel):
    """One page of proposals; ``total`` counts every row matching the filters."""

    total: int
    limit: int
    offset: int
    items: list[TagMergeProposalDTO] = Field(default_factory=list)


class TagMergeDecisionCommand(BaseModel):
    """The archivist's verdict on one proposal. Approval records intent, it does not merge."""

    status: Literal["APPROVED", "REJECTED"]
    decided_by: str | None = Field(default=None, description="Who decided; free text until authentication exists.")
    note: str | None = Field(default=None, description="Why; kept for auditing.")


class MergeSuggestionRunResponse(BaseModel):
    """Result of one suggestion run over the tag catalog."""

    clusters_found: int
    persisted: int = Field(description="Rows written or refreshed; a decided proposal is never touched.")
    pending: int = Field(description="Proposals still waiting for a human decision.")
    flagged: int = Field(description="Pending proposals carrying at least one review flag.")


class TagMergeImpact(BaseModel):
    """One tag a merge would absorb, with what disappears along with it."""

    tag_id: int
    name: str
    document_count: int
    macro_category_id: int | None = None
    ai_confidence_score: float | None = None


class MergePlan(BaseModel):
    """
    Everything a merge would do, computed before anything is written.

    Read side of the operation: the dry-run returns it (trimmed) and the apply consumes it, so
    the preview cannot promise something different from what the merge does. It is the same
    lesson as the AI text composition living in one SQL expression.
    """

    canonical_id: int
    canonical_name: str
    canonical_document_count: int = 0
    ids_to_merge: list[int] = Field(default_factory=list)
    impacted: list[TagMergeImpact] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    # The same links, kept per absorbed tag: the ledger needs to know which document carried
    # which tag, because undo restores each tag's links exactly (the union would over-link).
    documents_by_tag: dict[int, list[str]] = Field(default_factory=dict)
    synonym_names: list[str] = Field(default_factory=list)
    repointed_synonyms: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    category_would_be_lost: bool = False

    @property
    def documents_updated(self) -> int:
        """Distinct documents the merge touches (the union, never the sum)."""
        return len(self.document_ids)

    @property
    def links_rewritten(self) -> int:
        """Links moved: one per document the absorbed tags carried."""
        return sum(member.document_count for member in self.impacted)


class MergePreviewCommand(BaseModel):
    """Asks what a merge would change. Either a persisted proposal or an ad-hoc pair."""

    proposal_id: int | None = None
    canonical_id: int | None = None
    ids_to_merge: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_source_of_truth(self) -> "MergePreviewCommand":
        if self.proposal_id is None and (self.canonical_id is None or not self.ids_to_merge):
            raise ValueError("either proposal_id or canonical_id + ids_to_merge is required")
        if self.proposal_id is not None and (self.canonical_id is not None or self.ids_to_merge):
            raise ValueError("proposal_id cannot be combined with canonical_id/ids_to_merge")
        return self


class MergePreviewResponse(BaseModel):
    """Dry-run report: what changes, what is lost and why the curator should look twice."""

    canonical_id: int
    canonical_name: str
    documents_updated: int
    links_rewritten: int
    tags_deleted: list[TagMergeImpact] = Field(default_factory=list)
    synonyms_created: list[str] = Field(default_factory=list)
    synonyms_repointed: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    category_would_be_lost: bool = False


# ==========================================
# MERGE APPLICATION, UNDO AND AUDIT (the ledger)
# ==========================================


class MergeBatchCommand(BaseModel):
    """
    Applies a set of proposals.

    The call itself is the archivist's decision for the clusters still pending, and the
    ledger it writes is what makes the decision reversible. A rejected cluster is never
    applied — rejecting is a decision too.
    """

    proposal_ids: list[int] = Field(min_length=1)
    changed_by: str | None = None
    note: str | None = None


class MergeBatchEntry(BaseModel):
    """One cluster ready to be applied, with its plan already computed."""

    proposal_id: int
    cluster_fingerprint: str | None = None
    plan: MergePlan


class MergeBatchApplied(BaseModel):
    """A cluster that was applied, with the ledger handles to undo it."""

    proposal_id: int
    merge_ids: list[int] = Field(default_factory=list)
    documents_updated: int = 0
    tags_deleted: int = 0


class MergeBatchFailure(BaseModel):
    """A cluster that was not applied, and why. The others are unaffected."""

    proposal_id: int
    error: str


class BatchMergeResponse(BaseModel):
    """Per-cluster report: one bad cluster must not roll back the good ones."""

    applied: list[MergeBatchApplied] = Field(default_factory=list)
    failed: list[MergeBatchFailure] = Field(default_factory=list)


class MergeLogEntryDTO(BaseModel):
    """One absorbed tag in the ledger: what was merged, by whom, and whether it was undone."""

    merge_id: int
    cluster_fingerprint: str | None = None
    canonical_id: int | None = None
    canonical_name: str
    absorbed_tag_id: int
    absorbed_name: str
    document_count: int = 0
    repointed_synonym_names: list[str] = Field(default_factory=list)
    synonym_created: bool = True
    changed_by: str | None = None
    changed_at: datetime | None = None
    note: str | None = None
    undone_at: datetime | None = None
    undone_by: str | None = None

    @property
    def is_undone(self) -> bool:
        return self.undone_at is not None


class MergeLogListResponse(BaseModel):
    """One page of the audit trail, with the total matching the same filters."""

    total: int
    limit: int
    offset: int
    items: list[MergeLogEntryDTO] = Field(default_factory=list)


class MacroCategorySuggested(BaseModel):
    topic_id: int
    suggested_name: str
    estimate_count: int
    real_samples: list[str] = Field(default_factory=list)


class MacroCategoriesSuggestionResponse(BaseModel):
    total_suggestions: int
    categories: list[MacroCategorySuggested]
    message: str | None = None


class ArchiveMacroCategoryEntityDTO(BaseModel):
    category_id: int
    name: str
    description: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ArchiveTagDTO(BaseModel):
    """
    Strict contract for creating Tags (Taxonomy).

    Ensures that the classification models (e.g. mDeBERTa) deliver
    consistent categories accompanied by their confidence metric
    for observability metrics.
    """

    name: TagName = Field(description="The associated keyword or concept, preferably in lowercase.")
    macro_category_id: int | None = Field(
        default=None, description="Id linking to the main semantic drawer (e.g. Urbanism, Health)"
    )
    ai_confidence_score: float | None = Field(
        default=None, description="Degree of certainty of the AI model (0.0 to 1.0 or 0 to 100)."
    )

    model_config = ConfigDict(from_attributes=True)


class TagIdentity(BaseModel):
    """Lightweight read view of a tag used by write-side flows (merge, lookups)."""

    tag_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)

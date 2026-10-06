from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, computed_field

from memoria_curitibana.domains.archive.schemas.types import EntityName

# Who recorded a NER exclusion: a human curator or the LLM conflict judge.
NerExclusionSource = Literal["JUDGE", "HUMAN"]

#: The two axes of a tag x entity collision, who may decide it, and the two governance writes
#: a verdict can plant. Declared once so the DTOs, the plan and the ledger cannot disagree.
ConflictWinner = Literal["TAG", "ENTITY"]
ConflictDecider = Literal["JUDGE", "HUMAN"]
ConflictBanKind = Literal["NER_EXCLUSION", "STOPWORD"]


class NerSynonymRule(TypedDict):
    """
    Phrase pattern fed to spaCy's EntityRuler.

    ``pattern`` is the synonym spelling, ``label`` is the entity type and ``id``
    is the canonical entity name that spaCy exposes as ``ent_id_``.
    """

    pattern: str
    label: str
    id: str


class ArchiveEntityDTO(BaseModel):
    """
    Data contract for Named Entities (NER).

    Ensures that the extractors (such as spaCy) return entities
    standardized and validated against the types allowed in the domain
    before persistence.
    """

    name: EntityName = Field(description="Clean, formatted name of the entity.")
    entity_type: Literal["PER", "ORG", "LOC"] = Field(
        description="Entity type. Restricted to Person, Organization or Location."
    )

    model_config = ConfigDict(from_attributes=True)


class EntityIdentity(BaseModel):
    """Lightweight read view of an entity used by write-side flows (merge, lookups)."""

    entity_id: int
    name: str
    entity_type: str

    model_config = ConfigDict(from_attributes=True)


class EntitySimilarity(BaseModel):
    entity_id: int
    name: str
    entity_type: str
    similarity: float

    model_config = ConfigDict(from_attributes=True)


class EntityPairSimilarity(BaseModel):
    id_1: int
    name_1: str
    type_1: str
    id_2: int
    name_2: str
    type_2: str
    similarity: float

    model_config = ConfigDict(from_attributes=True)


class EntitySimilarityResponse(BaseModel):
    mode: Literal["all", "specific"]
    data: list[EntitySimilarity | EntityPairSimilarity]

    @classmethod
    def from_payload(cls, payload: list[EntitySimilarity | EntityPairSimilarity]) -> "EntitySimilarityResponse":
        if not payload:
            return cls(mode="all", data=[])

        first_item = payload[0]

        if isinstance(first_item, EntitySimilarity):
            return cls(mode="specific", data=payload)

        elif isinstance(first_item, EntityPairSimilarity):
            return cls(mode="all", data=payload)

        raise ValueError("Tipo de payload desconhecido")


class EntityMergeResponse(BaseModel):
    documents_updated: int
    entities_deleted: int

    model_config = ConfigDict(from_attributes=True)


class EntityRelevance(BaseModel):
    entity_id: int
    name: str
    entity_type: str
    total_usage: int

    model_config = ConfigDict(from_attributes=True)


class EntityRelevanceResponse(BaseModel):
    data: list[EntityRelevance]


class CrossDomainConflict(BaseModel):
    """
    One live collision, with whatever has already been decided about it.

    The similarity alone is not the whole story, and reading only it is what hid the judge's work:
    ``archive_ai_review_queue`` holds the verdict for every pair the judge evaluated (including the
    ones it auto-resolved, whose losing row no longer exists), and the resolution ledger holds what
    was written. Both travel here so the screen can show "already decided, by whom, with which
    confidence" instead of asking the archivist to decide it again.

    ``pair_kind`` separates the two very different populations the trigram join returns: an
    ``EXACT_NAME`` pair is the same spelling living on both axes (5.050 of them on the real
    collection — a *structural* question), while a ``NEAR_DUPLICATE`` is the same word written
    differently (122, mostly street abbreviations — a *spelling* question). Mixed together they
    made a 5.408-card queue in which the archivist could not see the real work.
    """

    tag_id: int
    tag_name: str
    entity_id: int
    entity_name: str
    entity_type: str
    similarity: float

    #: The judge's verdict, when the pair is in the review queue. ``None`` means never judged.
    judge_winner: ConflictWinner | None = None
    judge_confidence: float | None = None
    judge_reason: str | None = None
    judge_status: str | None = None

    #: The write, when the pair was already resolved. ``resolved_undone`` keeps the trail visible:
    #: an undone resolution is history, not a pending decision.
    resolution_id: int | None = None
    resolution_winner: ConflictWinner | None = None
    resolution_source: ConflictDecider | None = None
    resolved_undone: bool = False

    @computed_field
    @property
    def pair_kind(self) -> Literal["EXACT_NAME", "NEAR_DUPLICATE"]:
        """
        Which of the two populations the pair belongs to, derived from the score itself.

        A computed field rather than a column or a plain attribute, because it *is* the similarity:
        ``pg_trgm`` scores 1 exactly when the two spellings are the same word, so keeping the two as
        separate values would be an invitation for them to disagree. It is in the payload because the
        screen's whole job is to let the archivist open one population at a time.
        """
        return "EXACT_NAME" if self.similarity == 1 else "NEAR_DUPLICATE"


class CrossDomainConflictPage(BaseModel):
    """One page of the live scan, with the total for the same filters."""

    total: int
    limit: int
    offset: int
    items: list[CrossDomainConflict] = Field(default_factory=list)
    #: Counts by pair kind for the **whole** filtered set, not the page: the screen's
    #: "122 grafias diferentes / 5.050 nomes idênticos" cannot be derived from a page.
    exact_name_count: int = 0
    near_duplicate_count: int = 0
    #: How many of the filtered pairs already carry a judge verdict or a resolution.
    judged_count: int = 0


class ConflictResolutionPlan(BaseModel):
    """
    Everything a resolution would do, computed before anything is written.

    Single definition of the operation: ``POST /conflicts/resolve/preview`` returns it and the apply
    executes it, so the dry run cannot promise a different number from the write. The same lesson as
    ``MergePlan`` and the AI text composition living in one SQL expression.

    One plan carries **both** verdicts, because the archivist's question is comparative — "if the tag
    wins I lose the entity and gain N links; if the entity wins, the reverse" — and computing only
    the chosen side would force two round trips to answer it.
    """

    tag_id: int
    tag_name: str
    tag_document_count: int = 0
    entity_id: int
    entity_name: str
    entity_type: str
    entity_document_count: int = 0
    similarity: float = 0.0

    #: Whether each side still exists. A pair whose loser was already deleted cannot be resolved
    #: again, and the preview has to say that instead of offering a button that answers 404.
    tag_alive: bool = True
    entity_alive: bool = True
    #: Already decided (judge or human) or already written. The screen must not offer a second
    #: verdict over a settled pair without saying so.
    already_resolved: bool = False
    judge_winner: ConflictWinner | None = None
    judge_confidence: float | None = None
    judge_reason: str | None = None

    #: What each verdict would do. ``*_documents_transferred`` counts the links this resolution
    #: would **create**; ``*_documents_already_linked`` counts the documents that already carry the
    #: winner and are therefore untouched. The two together are the loser's documents.
    tag_wins_documents_transferred: int = 0
    tag_wins_documents_already_linked: int = 0
    tag_wins_loses: str | None = None
    tag_wins_ban_term: str | None = None
    tag_wins_ban_exists: bool = False

    entity_wins_documents_transferred: int = 0
    entity_wins_documents_already_linked: int = 0
    entity_wins_loses: str | None = None
    entity_wins_ban_term: str | None = None
    entity_wins_ban_exists: bool = False

    #: The pair is not resolvable at all (one side is gone), so neither verdict is offered.
    resolvable: bool = True
    blocker: str | None = None


class ConflictResolutionLogEntry(BaseModel):
    """One resolution in the ledger: what was written, by whom, and whether it was undone."""

    resolution_id: int
    winner: ConflictWinner
    source: ConflictDecider
    tag_id: int
    tag_name: str
    entity_id: int
    entity_name: str
    entity_type: str
    documents_transferred: int = 0
    ban_kind: ConflictBanKind | None = None
    ban_term: str | None = None
    ban_created: bool = False
    decided_by: str | None = None
    decided_at: datetime | None = None
    note: str | None = None
    undone_at: datetime | None = None
    undone_by: str | None = None
    #: Whether the row this resolution deleted is back. Derived on read, never stored.
    loser_restored: bool = False

    @computed_field
    @property
    def is_undone(self) -> bool:
        """Computed so the front reads one definition instead of comparing a timestamp itself."""
        return self.undone_at is not None


class ConflictResolutionLogListResponse(BaseModel):
    """One page of the audit trail, with the total matching the same filters."""

    total: int
    limit: int
    offset: int
    items: list[ConflictResolutionLogEntry] = Field(default_factory=list)


class JudgedConflict(BaseModel):
    """
    One pair the judge evaluated, read from the review queue instead of the live scan.

    This is the read that was missing: 84 of the 88 decisions on the real collection were
    auto-resolutions whose losing row was deleted, so the live trigram scan cannot return them —
    the judge's work was invisible exactly where it was most complete.

    ``tag_alive``/``entity_alive`` are computed on read, like the merge proposals' ``members_alive``:
    the queue row outlives the vocabulary it names, and a decision about a pair that no longer exists
    is history. ``applicable`` is the single definition of "there is still work here" — both sides
    alive and nothing written — used by the screen and never recomputed by it.
    """

    queue_id: int
    tag_id: int
    tag_name: str
    entity_id: int
    entity_name: str
    entity_type: str
    judge_winner: ConflictWinner | None = None
    judge_confidence: float | None = None
    judge_reason: str | None = None
    judge_status: str
    tag_alive: bool = False
    entity_alive: bool = False
    resolution_id: int | None = None
    resolution_undone: bool = False

    @computed_field
    @property
    def applicable(self) -> bool:
        """
        Both sides alive and nothing written: the only state with work left.

        The single definition of "there is still something to decide here", exposed in the payload
        so the screen and the counter cannot drift apart on what "pending" means.
        """
        return self.tag_alive and self.entity_alive and self.resolution_id is None


class JudgedConflictPage(BaseModel):
    """One page of the judge's decisions, with the totals the screen cannot derive from a page."""

    total: int
    limit: int
    offset: int
    items: list[JudgedConflict] = Field(default_factory=list)
    #: Counts over the **whole** queue, not the page.
    auto_resolved: int = 0
    sent_to_human: int = 0
    tag_wins: int = 0
    entity_wins: int = 0
    still_applicable: int = 0


class ConflictResolutionData(BaseModel):
    winner: Literal["TAG", "ENTITY"]
    documents_transferred: int
    #: The ledger row, so the screen can offer the undo of the write it just made.
    resolution_id: int | None = None
    ban_kind: ConflictBanKind | None = None
    ban_term: str | None = None


class NerExclusion(BaseModel):
    """A durable decision that a spelling belongs to the TAG axis, not to NER."""

    term: str
    reason: str | None
    source: NerExclusionSource
    tag_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ROUTE RESPONSES (the shape the API answers with)
# ==========================================
#
# These routes returned a plain ``dict``, which the generated client cannot see: the curator front
# would read them through a cast, and a renamed key would reach the screen as ``undefined``. The
# keys are the ones those routes already sent.


class NerExclusionBanResponse(BaseModel):
    """Terms banned from NER, and how many already-extracted entities the ban purged."""

    message: str
    entities_deleted: int


class NerExclusionRemovalResponse(BaseModel):
    """The ban was lifted: the extractor will consider those spellings again."""

    message: str
    removed: int


class OrphanEntityPurgeResponse(BaseModel):
    """Delete of the entities no description carries."""

    message: str
    entities_deleted: int


class EntityReclassifyResponse(BaseModel):
    """
    The new type, and the promise that matters: reclassifying writes the anchoring synonym.

    It is not a label change. The synonym makes the extractor obey the decision on every
    future run, which is why the screen has to say so.
    """

    message: str
    new_type: Literal["ORG", "PER", "LOC"]


class EntityDeleteResponse(BaseModel):
    """One entity removed from the vocabulary."""

    message: str

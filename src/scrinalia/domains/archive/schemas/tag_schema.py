from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scrinalia.core.author import Author
from scrinalia.domains.archive.models.enums import StopwordMatch, StopwordsScope
from scrinalia.domains.archive.schemas.responses import RouteMessageCode, RouteResponse
from scrinalia.domains.archive.schemas.types import TagName


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
    macro_category_name: str | None = None
    ai_confidence_score: float | None = None

    model_config = ConfigDict(from_attributes=True)


class TagMergeMember(BaseModel):
    """One tag inside a proposed merge cluster."""

    tag_id: int
    name: str
    document_count: int


class TagSearchResult(BaseModel):
    """
    A tag as the type-ahead sees it: the identity, its weight and the drawer it sits in.

    ``document_count`` is what decides between two spellings of the same word, and
    ``macro_category_name`` is the badge the curator already knows from the list — without it the
    suggestion is a name with no context, and the wrong one gets picked.
    """

    tag_id: int
    name: str
    document_count: int = 0
    macro_category_id: int | None = None
    macro_category_name: str | None = None


class TagCurationCommand(BaseModel):
    """
    Moves one tag to a subject drawer, or takes it out of every drawer.

    ``macro_category_id`` is required and nullable on purpose: ``None`` is the decision "this tag
    is not a subject", not the absence of a decision. A default would make the two
    indistinguishable, and the difference is the whole point of the command.
    """

    macro_category_id: int | None = Field(description="Drawer to move the tag into; ``null`` orphans it again.")
    changed_by: Author | None = Field(
        default=None, description="Who decided: the account when there is one, the name alone when there is not."
    )
    note: str | None = Field(default=None, description="Why; kept in the tag's ledger.")


class TagCurationResult(BaseModel):
    """The tag after the decision, plus whether a person is now responsible for its drawer."""

    tag_id: int
    name: str
    macro_category_id: int | None = None
    macro_category_name: str | None = None
    #: True once a curator classified it: the AI's confidence is cleared at that point, because the
    #: number described a decision that no longer stands.
    human_classified: bool = False
    #: True when the same decision registered the term as "not a subject" for the classifier. It is
    #: part of the **outcome** and not an internal detail: the screen reports what it wrote, and the
    #: verdict is durable only because of this half — ``macro_category_id=null`` alone comes back to
    #: the classifier on the next run, when the label set changes.
    subject_excluded: bool = False


# ==========================================
# THE CATALOGUE OF TAGS, BY THE STATE OF THEIR SUBJECT
# ==========================================


class TagCatalogRow(BaseModel):
    """
    One tag of the catalogue, with everything needed to decide about it without a second read.

    Deliberately not ``TagSearchResult``: this row explains **why** the tag is where it is. The
    type-ahead answers "which spelling did I mean?" and pays for one grouped count; this one carries
    the confidence the classifier gave up on and the term's verdict, which is what lets the screen
    show a state instead of an absence. The two share the definition of ``document_count``
    (documents linked to the tag), and the count is the same one the drawer badge uses.
    """

    tag_id: int
    name: str
    document_count: int = 0
    macro_category_id: int | None = None
    macro_category_name: str | None = None
    #: What the classifier scored before refusing to file it; ``None`` when it never ran or when a
    #: person has since decided, which clears the number.
    ai_confidence_score: float | None = None
    #: The term is registered as "not a subject", so the classifier does not guess at it again and
    #: its spelling is banned from becoming a tag again.
    subject_excluded: bool = False


class TagCatalogResponse(BaseModel):
    """One page of the catalogue, with the total for the same filter."""

    total: int = 0
    limit: int = 25
    offset: int = 0
    items: list[TagCatalogRow] = Field(default_factory=list)


# ==========================================
# STOPWORDS (the curated "this is not a term" list)
# ==========================================


class StopwordDTO(BaseModel):
    """
    One banned term, **which axis it was banned from** and who planted the ban.

    The scope is not decoration: ``TagRepository.get_stopwords()`` reads only ``TAG``/``ALL``, so an
    ``ENTITY``-scoped ban cannot make the subject purge delete a tag the curator kept. The screen has
    to show the scope, or the two mechanisms look like one list and the archivist stops trusting it.
    ``source`` is the provenance the purge preview names (``HUMAN`` typed on the Stopwords tab,
    ``CONFLICT`` planted by a tag x entity resolution, ``EXCLUSION`` confirmed on the "not a subject"
    screen), because one of the three is a consequence and the other two are acts.
    """

    word: str
    scope: StopwordsScope
    source: str = "HUMAN"
    #: How the ban matches an extracted name (#160): ``TOKEN`` also blocks the names that contain it,
    #: ``EXACT`` blocks the spelling alone. Only the ENTITY/ALL axes read it.
    match_mode: StopwordMatch

    model_config = ConfigDict(from_attributes=True)


class StopwordCreateCommand(BaseModel):
    """Terms to ban. ``TAG`` by default, because that is the axis this catalog governs."""

    words: list[str] = Field(min_length=1, description="Termos a banir (normalizados ao gravar).")
    # No ``description``: see ``StopwordCreateRequest`` — a field description leaks into the shared
    # enum schema and makes the generated contract depend on the hash seed.
    scope: StopwordsScope = Field(default=StopwordsScope.TAG)


class StopwordRemovalCommand(BaseModel):
    """Terms to un-ban. With no scope, the word leaves every axis it was banned from."""

    words: list[str] = Field(min_length=1)
    scope: StopwordsScope | None = Field(default=None)


class StopwordPurgeItem(BaseModel):
    """One tag the purge would delete, with the exact state the undo has to rebuild."""

    tag_id: int
    name: str
    document_ids: list[str] = Field(default_factory=list, description="The documents that carried it.")
    synonym_names: list[str] = Field(default_factory=list, description="The spellings that pointed at it.")
    macro_category_id: int | None = None
    macro_category_name: str | None = None
    ai_confidence_score: float | None = None
    execution_log: dict[str, str] | None = None
    created_at: datetime | None = None
    #: Who planted the ban that is about to delete this tag: the column the preview reports and the
    #: ledger does not need to restore, because the undo deliberately does not lift the ban.
    source: str = "HUMAN"


class StopwordPurgePlan(BaseModel):
    """
    Everything the purge would delete, computed before anything is written.

    Single definition of the operation: the preview reads it and the write consumes it, so the
    two cannot disagree about which tags die — the same rule ``TagRepository.plan_merge``
    follows. The items carry the snapshot the ledger records, which is why the dry run and the
    write are one computation instead of two that happen to agree today.
    """

    stopwords: list[str] = Field(default_factory=list)
    items: list[StopwordPurgeItem] = Field(default_factory=list)

    @property
    def total_tags(self) -> int:
        return len(self.items)

    @property
    def total_documents(self) -> int:
        """Documents that lose a tag, counted per tag: one document can lose two."""
        return sum(len(item.document_ids) for item in self.items)


class StopwordPurgeTag(BaseModel):
    """One tag the purge would delete, with the weight that makes the loss concrete."""

    tag_id: int
    name: str
    document_count: int = 0
    macro_category_name: str | None = None
    #: ``HUMAN``, ``CONFLICT`` or ``EXCLUSION``: the origin of the ban that would delete it, so the
    #: screen can separate the terms banned with the archive in mind from the ones typed by hand.
    source: str = "HUMAN"


class StopwordPurgePreview(BaseModel):
    """
    What the purge would destroy, before it destroys it.

    The purge keeps a ledger now (:class:`ArchiveStopwordPurgeLog`), so ``reversible`` is true:
    the write is logged per deleted tag before anything changes and the undo restores the row,
    its links and its spellings. The preview remains the step, not a convenience — the ledger
    makes the loss recoverable, it does not make it invisible.
    """

    stopwords: list[str] = Field(
        default_factory=list, description="The TAG/ALL terms the purge would act on, in lowercase."
    )
    tags: list[StopwordPurgeTag] = Field(default_factory=list)
    total_tags: int = 0
    total_documents: int = Field(default=0, description="Documents that lose a subject tag.")
    reversible: bool = Field(default=True, description="True: the ledger restores the tags and their links.")


class StopwordPurgeLogEntryDTO(BaseModel):
    """One deleted tag in the ledger: what was purged, by whom, and whether it was restored."""

    purge_id: int
    purged_tag_id: int
    purged_name: str
    document_count: int = 0
    synonym_names: list[str] = Field(default_factory=list)
    macro_category_name: str | None = None
    changed_by: str | None = None
    changed_at: datetime | None = None
    undone_at: datetime | None = None
    undone_by: str | None = None

    @property
    def is_undone(self) -> bool:
        return self.undone_at is not None


class StopwordPurgeLogListResponse(BaseModel):
    """One page of the purge ledger, with the total matching the same filters."""

    total: int
    limit: int
    offset: int
    items: list[StopwordPurgeLogEntryDTO] = Field(default_factory=list)


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
    status: Literal["SUGGESTED", "APPROVED", "REJECTED", "APPLIED"]
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None

    # --- Whether there is still anything to do -------------------------------------------------
    # The members are a *snapshot* and carry no foreign key, so they outlive the tags they name.
    # Without these two counts the catalogue keeps offering an apply that can only fail, which is
    # what made a batch of 20 already-merged clusters look like 20 errors.
    members_alive: int = Field(default=0, description="Membros que ainda existem no acervo.")
    canonical_alive: bool = Field(default=True, description="Se a tag canônica ainda existe.")
    applicable: bool = Field(
        default=False,
        description="Há tag para absorver: a canônica existe e sobrou ao menos um membro além dela.",
    )

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
    decided_by: Author | None = Field(
        default=None, description="Who decided: the account when there is one, the name alone when there is not."
    )
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
    changed_by: Author | None = None
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
    #: Clusters that needed no write because an earlier merge already absorbed their members.
    #: Reported apart from ``failed``: nothing went wrong, there was simply nothing left to do.
    skipped: list[MergeBatchFailure] = Field(default_factory=list)


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
    """
    What the clustering run found, and the warning when there was too little text to cluster.

    Not a :class:`RouteResponse`: this route succeeds with an empty answer, so the sentence is
    optional. The code is optional for the same reason — absent means "it ran and found something",
    present means "it could not", and a translation catalogue needs to tell those apart.
    """

    total_suggestions: int
    categories: list[MacroCategorySuggested]
    code: RouteMessageCode | None = None
    message: str | None = None


class ArchiveMacroCategoryEntityDTO(BaseModel):
    category_id: int
    name: str
    description: str | None
    #: The proposition the NLI model reads; ``None`` falls back to ``name``.
    classifier_label: str | None = None
    is_active: bool
    #: How many **descriptions** carry at least one tag in this drawer. Derived on read: the screen
    #: shows the weight of each drawer, and a count that is stored would go stale the moment a tag
    #: moves — which is now something a curator does from the dossier.
    document_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SubjectExclusionSuggestion(BaseModel):
    """
    A term the deterministic guard already refuses, with the evidence around it.

    The route does **not** invent a verdict for the terms no rule reaches — ``pessoas``,
    ``vista aérea``, ``exemplo lugar`` are semantic calls, and the measurement says the model cannot
    abstain on exactly those (asked to choose, it chooses confidently and wrongly). What it does is
    make the guard's existing verdict legible: it has been silently skipping these terms inside
    ``worker_macro_category`` while ``source='RULE'`` sat unused in the schema.

    The evidence travels with the candidate because the archivist is deciding, not confirming:
    ``document_count`` is the weight at stake, ``is_place_term`` says the term is a place — the entity
    axis owns it, which is a different statement from "goes nowhere" (ADR 0013) — and
    ``also_an_entity`` says the same spelling already lives on the NER axis, which is the collision
    screen's business rather than this one's. ``macro_category_name`` and ``already_banned`` are the
    two facts that change what the button does: a term whose tag sits in a drawer is refused, and
    confirming a term bans its spelling from becoming a tag again.
    """

    term: str
    #: Why the guard refuses it: ``PLACEHOLDER``/``YEAR``/``MEASURE``/``STREET``/``PERSON``. For a
    #: term already recorded by hand, with no shape to report, ``RECORDED`` — the route never invents
    #: a shape, and the guard's reason stays visible even after the decision was taken.
    signal: str
    document_count: int = 0
    #: The term is a place: a street spelling or a toponym of the collection's own vocabulary. The
    #: entity axis is where it goes; the subject axis simply stops guessing at it.
    is_place_term: bool = False
    #: The same spelling exists as a named entity: that is a tag x entity collision, not a subject.
    also_an_entity: bool = False
    word_count: int = 1
    #: Already recorded as not-a-subject. The screen shows them apart instead of offering them again.
    already_excluded: bool = False
    #: The tag sits in a subject drawer, so the write refuses the term and names the drawer here
    #: instead of un-filing a human verdict (issue #83, option C).
    macro_category_id: int | None = None
    macro_category_name: str | None = None
    #: Its spelling is already banned from becoming a tag again, so confirming adds nothing there.
    already_banned: bool = False


class SubjectExclusionSuggestionResponse(BaseModel):
    """The computed candidates, with the totals the screen cannot derive from a page."""

    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[SubjectExclusionSuggestion] = Field(default_factory=list)
    #: How many candidates there are in total, before the page, and how many are already recorded.
    candidate_count: int = 0
    already_excluded_count: int = 0
    #: One count per signal, over the whole candidate set.
    by_signal: dict[str, int] = Field(default_factory=dict)
    #: How many candidates the PLACE facet claims, so "excluir do assunto" is not read as "discard".
    place_count: int = 0


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


# ==========================================
# ROUTE RESPONSES (the shape the API answers with)
# ==========================================
#
# Every route that writes answers ``message`` plus what actually changed. They were plain
# ``dict`` returns until the curator front needed them: an untyped response is invisible to the
# generated client, so the screen would read it through a cast and a renamed key would only show
# up as ``undefined`` in the browser. The shape here is the one those routes already sent.


class TagMergeProposalDecisionResponse(RouteResponse):
    """The verdict was recorded. Approval is intent — the batch is what merges."""

    data: TagMergeProposalDTO


class TagMergeUndoResponse(RouteResponse):
    """The absorbed tag came back, exactly as the ledger remembered it."""

    data: MergeLogEntryDTO


class StopwordBanResponse(RouteResponse):
    """Terms banned. Banning deletes nothing: the purge is a separate, explicit step."""

    created: int


class StopwordRemovalResponse(RouteResponse):
    """Terms un-banned. The purge keeps a ledger, so this is no longer the only way back."""

    removed: int


class StopwordMatchResponse(RouteResponse):
    """The match mode of the given terms was changed. The bans and their origins stay."""

    updated: int


class StopwordPurgeResult(BaseModel):
    """What the purge did, as the repository reports it: the count and the ledger ids to undo."""

    tags_deleted: int = 0
    purge_ids: list[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class StopwordPurgeResponse(RouteResponse):
    """What the purge deleted, with the ledger ids the screen needs to offer the undo."""

    tags_deleted: int
    purge_ids: list[int] = Field(default_factory=list)


class StopwordPurgeUndoResponse(RouteResponse):
    """The purged tag came back, exactly as the ledger remembered it."""

    data: StopwordPurgeLogEntryDTO


class SubjectExclusionTarget(BaseModel):
    """
    One term the "not a subject" write would act on, or one it refuses.

    The refusal is the whole point of :class:`SubjectExclusionPlan`: a term whose tag already sits in
    a drawer is a subject question already answered, and the write that settles a *tag* is the tag
    catalogue's ``PATCH`` — a statement about a term must not un-file a human verdict (issue #83,
    option C). Everything else here is the evidence that makes the decision concrete, computed once
    and read by the preview and by the write.
    """

    term: str
    #: The guard's shape for the term, or ``None`` when the archivist typed it.
    signal: str | None = None
    #: The term is a place: a street spelling or a toponym of the collection's vocabulary.
    is_place_term: bool = False
    #: The same spelling already exists as a named entity — the entity axis owns what it is.
    also_an_entity: bool = False
    #: Documents that carry the tag, when there is one; the loss the purge would make real.
    document_count: int = 0
    tag_id: int | None = None
    #: Set only on a refused term: the drawer that has to be emptied first, on the tag catalogue.
    macro_category_id: int | None = None
    macro_category_name: str | None = None
    already_excluded: bool = False
    already_banned: bool = False


class SubjectExclusionPlan(BaseModel):
    """
    Everything the "not a subject" write would do, computed before anything is written.

    Single definition of the operation, like ``TagRepository.plan_merge``: the preview reads it and
    the write consumes it, so the dry run cannot promise another number. ``applicable`` is what the
    write will record — the exclusion and the ``TAG``-scoped ban — and ``blocked`` is what it refuses,
    each with the drawer in the way.
    """

    applicable: list[SubjectExclusionTarget] = Field(default_factory=list)
    blocked: list[SubjectExclusionTarget] = Field(default_factory=list)

    @property
    def total_applicable(self) -> int:
        return len(self.applicable)

    @property
    def total_blocked(self) -> int:
        return len(self.blocked)


class SubjectExclusionApplyResult(BaseModel):
    """What the write did: exclusions recorded, bans planted, and the terms it refused."""

    created: int = 0
    banned: int = 0
    blocked: list[SubjectExclusionTarget] = Field(default_factory=list)


class SubjectExclusionRemovalResult(BaseModel):
    """What the undo did: exclusions removed and the bans the exclusion itself had planted."""

    removed: int = 0
    unbanned: int = 0


class SubjectExclusionBanResponse(RouteResponse):
    """
    Terms declared not-a-subject: the classifier stops guessing at them.

    ``banned`` counts the spellings the same write banned from becoming a tag again — the half that
    keeps the next ingestion from recreating what was just decided — and ``blocked`` carries the
    terms whose tag is in a drawer, which the write refused instead of un-filing a human verdict.
    """

    created: int
    banned: int = 0
    blocked: list[SubjectExclusionTarget] = Field(default_factory=list)


class SubjectExclusionRemovalResponse(RouteResponse):
    """The decision was undone, the term is back in the queue and the ban it planted is lifted."""

    removed: int
    unbanned: int = 0

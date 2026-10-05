"""Read views and commands of the description hierarchy (Fase 2.5, H1—H3)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memoria_curitibana.domains.archive.domain.hierarchy import PlanStatus


# =============================================================================
# H1 — Level catalogue
# =============================================================================
class DescriptionLevelDTO(BaseModel):
    """One rung of the level catalogue."""

    level_id: int
    ordinal: int
    code: str
    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    requires_parent: bool
    allows_children: bool
    is_active: bool
    #: How many descriptions point at this rung. Derived on read; the catalogue never deletes a
    #: rung precisely because this number is what makes "deactivate instead" a real choice.
    document_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CreateDescriptionLevelCommand(BaseModel):
    """Registers a rung. The ordinals already taken are rejected, not reordered."""

    ordinal: int = Field(ge=0, description="Position on the ladder.")
    code: str = Field(min_length=1, max_length=20, description="Stable machine key, e.g. 'serie'.")
    name: str = Field(min_length=1, max_length=60, description="What the archivist sees.")
    description: str | None = Field(default=None, description="Curation-facing documentation.")
    aliases: list[str] = Field(default_factory=list, description="Alternative spellings accepted on match.")
    requires_parent: bool = Field(default=False, description="A node at this level may not be a root.")
    allows_children: bool = Field(default=True, description="A node at this level may have children.")


class UpdateDescriptionLevelCommand(BaseModel):
    """Partial update of a rung. ``ordinal`` is not editable: it would silently re-rank the tree."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = None
    aliases: list[str] | None = None
    requires_parent: bool | None = None
    allows_children: bool | None = None
    is_active: bool | None = None


# =============================================================================
# H2 — The tree
# =============================================================================
class HierarchyNodeSummary(BaseModel):
    """One description as a node of the arrangement."""

    description_id: str
    reference_code: str | None = None
    title: str | None = None
    level_id: int | None = None
    level: str | None = None
    parent_id: str | None = None
    path: str
    children_count: int = 0
    is_orphan: bool = Field(default=False, description="No parent while its level demands one.")


class HierarchyTreeResponse(BaseModel):
    """
    A flat, ``path``-ordered slice of the tree.

    Flat and not nested on purpose: the front-end renders a tree from ``parent_id``/``path``
    without a recursive schema, and a nested payload would have to be rebuilt for every filter
    the curator applies. ``root_id`` is ``None`` when the whole forest was returned.
    """

    root_id: str | None = None
    total: int = 0
    items: list[HierarchyNodeSummary] = Field(default_factory=list)


class HierarchyNodeDetail(BaseModel):
    """
    One description as a place in the arrangement: itself, where it hangs from, and what it holds.

    This is the read the individual edit needs (H5): before a curator moves a node or corrects its
    rung, they have to see the branch it sits on and what would travel with it.
    """

    node: HierarchyNodeSummary
    ancestors: list[HierarchyNodeSummary] = Field(default_factory=list, description="Root first.")
    children: list[HierarchyNodeSummary] = Field(default_factory=list)


class HierarchyDiagnostic(BaseModel):
    """One description flagged by the structural diagnosis."""

    description_id: str
    issue: str
    reference_code: str | None = None
    title: str | None = None
    level_id: int | None = None
    level: str | None = None
    path: str
    detail: dict[str, Any] = Field(default_factory=dict)


class HierarchyDiagnosticListResponse(BaseModel):
    """A page of diagnostics for one issue code, plus the total for the same filter."""

    issue: str
    total: int
    limit: int
    offset: int
    items: list[HierarchyDiagnostic]


class HierarchyDiagnosticSummary(BaseModel):
    """
    How many descriptions each structural problem flags, for the sections of the screen.

    Counts and no grand total on purpose: the issues **overlap** — a Dossiê at the root is both an
    ``ORPHAN`` and a ``DOSSIER_WITHOUT_PARENT``, and a description with no level is both an
    ``ORPHAN`` and an ``UNKNOWN_LEVEL`` — so adding them up would inflate the collection and
    produce a number no screen can use. Each count comes from the same predicate as its own page,
    which is what keeps the section header and its list from disagreeing.
    """

    counts: dict[str, int] = Field(
        default_factory=dict,
        description="One entry per issue the diagnostics endpoint accepts, zeroes included.",
    )


class HierarchyVocabulary(BaseModel):
    """
    The vocabularies the arrangement screens group by, so a front never embeds the enums.

    The codes travel from here to the UI as data: a status the screen does not know how to render
    can then be shown as an unknown code instead of being silently dropped by a hardcoded list.
    """

    issues: list[str] = Field(
        default_factory=list,
        description="Issues ``GET /hierarchy/diagnostics`` accepts, in the order the screen shows them.",
    )
    plan_statuses: list[str] = Field(default_factory=list, description="Lifecycle of a proposed rung.")
    plan_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Every flag a plan row's ``flags`` may carry, from the four vocabularies that write it: "
            "the proposal's, the near-duplicate issue, the ladder violation and the slicer's. "
            "All of it advisory, none of it a decision."
        ),
    )
    violations: list[str] = Field(
        default_factory=list,
        description="Why a move or a creation is refused, so the screen can explain the refusal.",
    )


class CreateHierarchyNodeCommand(BaseModel):
    """
    Creates an arrangement node that has no counterpart in the source.

    A fund, a section and a series are descriptions like any other, but the ingestion only ever
    delivers what the origin declared. Materialising the tree (H4) needs to create the rungs
    the codes imply and the source never sent; this is that write.
    """

    reference_code: str = Field(min_length=1, description="Code of the new node, e.g. 'BR PRADAP SMU'.")
    title: str = Field(min_length=1, description="Title of the node.")
    level_id: int | None = None
    parent_id: str | None = Field(default=None, description="Parent code holder; omit for a root.")
    scope_content: str | None = None
    changed_by: str | None = Field(default=None, description="Who created it; free text until auth exists.")
    note: str | None = None


class MoveNodeCommand(BaseModel):
    """
    Reparents and/or re-levels one description.

    Both fields are optional and independent: correcting the rung of a node and moving it are
    different decisions that happen to share a screen. Omitted means untouched.
    """

    new_parent_id: str | None = Field(default=None, description="New parent; ``None`` promotes to root.")
    level_id: int | None = None
    changed_by: str | None = None
    note: str | None = None


# =============================================================================
# H3 — Proposal (read-only)
# =============================================================================
class HierarchyProposalNode(BaseModel):
    """
    One node the reference codes imply, and everything the archivist needs to decide about it.

    The proposal never writes: it is the H4 screen's payload. ``ordinal_inferred`` is the field
    that keeps it honest — the depth of a code does **not** determine the ISAD(G) level in this
    collection (measured: five tokens hold Items, a Série and a Seção), so an ordinal no
    declared record anchors is a guess and says so.
    """

    code: str
    depth: int
    parent_code: str | None = None
    status: str = Field(description="EXISTS | TO_CREATE | AMBIGUOUS")
    proposed_level_id: int | None = None
    proposed_level_code: str | None = Field(default=None, description="Catalogue code of the proposed rung.")
    ordinal_inferred: bool = True
    document_count: int = 0
    #: The levels the descendants declare, so a conflict is visible before the rung is chosen.
    declared_levels: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    suggested_name: str | None = None
    existing_description_id: str | None = None
    sample_description_ids: list[str] = Field(default_factory=list)


class HierarchyProposalResponse(BaseModel):
    """The whole proposed arrangement for the current collection. Read-only, computed on demand."""

    total_codes: int
    structural_codes: int
    total_nodes: int
    existing_nodes: int
    nodes_to_create: int
    ambiguous_nodes: int
    flagged_nodes: int
    flags: dict[str, int] = Field(default_factory=dict, description="How many nodes carry each flag.")
    unparsed_codes: list[str] = Field(default_factory=list, description="Codes the slicer could not read cleanly.")
    nodes: list[HierarchyProposalNode] = Field(default_factory=list)


class HierarchyProposalCommand(BaseModel):
    """
    Options of the proposal run.

    The response carries no timestamp on purpose: the run is read-only and computed on demand,
    so a "generated at" would be the only non-deterministic field of a payload the archivist is
    meant to compare against the collection as it is now.
    """

    include_existing: bool = Field(default=True, description="Include codes that already have a record.")
    limit: int = Field(default=500, ge=1, le=5000, description="Cap on returned nodes.")


# =============================================================================
# H4 — Materialisation of the tree, driven by a human decision
# =============================================================================
class HierarchyNodePlanDTO(BaseModel):
    """
    One rung the codes imply, with the evidence and the archivist's decision about it.

    ``status`` is what tells a proposal from a statement: while it is ``SUGGESTED`` the level and
    the title are the machine's, and once it leaves ``SUGGESTED`` they are the archivist's and a
    new suggestion run will not touch them.
    """

    plan_id: int
    code: str
    depth: int
    parent_code: str | None = None

    document_count: int = 0
    declared_levels: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    sample_description_ids: list[str] = Field(default_factory=list)
    existing_description_id: str | None = None

    level_id: int | None = None
    level: str | None = None
    title: str | None = None
    reference_code: str | None = None

    status: str = "SUGGESTED"
    collapse_into_code: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None

    materialised_description_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class HierarchyPlanSuggestionResponse(BaseModel):
    """What one suggestion run changed. A decision already taken is never overwritten."""

    created: int
    refreshed: int
    preserved: int = Field(description="Rungs whose decision was respected and left untouched.")
    total: int


class HierarchyPlanListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[HierarchyNodePlanDTO]
    #: The whole catalogue counted by verdict, not just the filtered page: the screen's progress
    #: ("34 de 52 decididos") is a statement about every rung, so it cannot be derived from a page.
    status_counts: dict[str, int] = Field(default_factory=dict)


class HierarchyPlanDecisionCommand(BaseModel):
    """
    The archivist's verdict on one rung.

    ``collapse_into_code`` is the operation the code cannot do for itself: ``AL`` and ``CONSTR``
    are one level, and the machine has no way to know it. The same field resolves a rung whose
    documents really belong under an existing record spelled one letter differently.
    """

    status: PlanStatus
    level_id: int | None = None
    title: str | None = Field(default=None, max_length=300)
    reference_code: str | None = Field(default=None, max_length=500)
    collapse_into_code: str | None = Field(
        default=None,
        description="This rung IS that rung. Send an empty string to undo a previous collapse.",
    )
    decided_by: str | None = None
    note: str | None = None


class HierarchyMaterialisationItem(BaseModel):
    """What the run would do with one rung."""

    code: str
    action: str = Field(description="CREATE | ADOPT | ALREADY")
    node_description_id: str | None = None
    parent_code: str | None = None
    level: str | None = None
    title: str | None = None
    document_count: int = 0
    sample_description_ids: list[str] = Field(default_factory=list)
    rooted_early: bool = Field(
        default=False,
        description="Its parent rung is proposed but not approved, so the node would sit at the root.",
    )


class HierarchyMaterialisationPreview(BaseModel):
    """
    The dry run: exactly what the run would create and move, and nothing else.

    It is computed by the same planner the apply executes, so the numbers cannot diverge from the
    write — a dry run that lies is worse than no dry run.
    """

    nodes_to_create: int
    nodes_to_adopt: int
    nodes_already_materialised: int
    documents_to_attach: int
    documents_already_placed: int
    remaining_orphans: int = Field(
        description="Descriptions that would still have no parent because no rung of their code is approved."
    )
    items: list[HierarchyMaterialisationItem] = Field(default_factory=list)


class HierarchyMaterialisationRequest(BaseModel):
    """Who authorised the run, and why. The decision itself lives in the plan rows."""

    changed_by: str | None = None
    note: str | None = None
    limit: int = Field(default=500, ge=1, le=5000, description="Cap on the items carried in the preview.")


class HierarchyMaterialisationResult(BaseModel):
    """What one applied run did, and the ledger entry that can reverse it."""

    materialisation_id: int
    created_nodes: int
    adopted_nodes: int
    documents_attached: int
    rung_map_size: int
    items: list[HierarchyMaterialisationItem] = Field(default_factory=list)


class HierarchyMaterialisationLogDTO(BaseModel):
    """One ledger entry: what a run did and whether it has been reversed."""

    materialisation_id: int
    created_nodes: list[dict] = Field(default_factory=list)
    rung_map: dict = Field(default_factory=dict)
    changed_rows: int = 0
    changed_by: str | None = None
    changed_at: datetime
    note: str | None = None
    undone_at: datetime | None = None
    undone_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class HierarchyMaterialisationLogListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[HierarchyMaterialisationLogDTO]

"""Read views and commands of the description hierarchy (Fase 2.5, H1—H3)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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

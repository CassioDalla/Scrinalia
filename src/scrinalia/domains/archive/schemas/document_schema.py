from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from scrinalia.core.config import storage_configured
from scrinalia.domains.archive.models import ArchiveEntityOrigin, ArchiveReviewStatus
from scrinalia.domains.archive.schemas.responses import RouteResponse


class ArchiveDocumentDTO(BaseModel):
    """
    Strict Insert/Update Contract for the Archive Layer.

    Acts as the guardian of the fact table's integrity. Ensures that migration
    scripts and multiple Artificial Intelligence workers carry complete, typed
    payloads when updating the document's enrichment state.
    """

    description_id: str = Field(description="ID inherited from Silver.")
    origin_code: str | None = Field(
        default=None, description="Ingestion origin that produced the staging record, when known."
    )
    original_title: str = Field(description="Original title from Silver.")
    document_date: date | None = Field(default=None, description="Document date.")
    #: The date as the source spelled it (``Década de 1980``, ``1951-1953``). The parsed column is
    #: approximate by design, so the spelling is the only evidence of what the record says.
    date_expression: str | None = Field(default=None, description="Date as the source spelled it.")
    summary: str | None = Field(default=None, description="Document summary.")
    staging_content_hash: str = Field(description="Lineage control hash and change detection (CDC).")
    original_url: str | None = Field(default=None, description="URL of the page the record was read from.")
    original_thumbnail_url: str | None = Field(
        default=None, description="Public download link of the thumbnail at the source."
    )
    storage_thumbnail_uri: str | None = Field(
        default=None, description="URI or internal path of the file saved in the Object Storage"
    )

    # --- ISAD(G) Standard Metadata ---
    reference_code: str | None = Field(default=None, description="Archival reference code.")
    #: Rung of the level catalogue resolved from the declared text. ``None`` when the source
    #: declares a level the catalogue does not know: the load does **not** fail, the node is
    #: left unclassified and the diagnostics report it as ``UNKNOWN_LEVEL``.
    level_id: int | None = Field(default=None, description="Description level (catalogue FK).")
    producers: str | None = Field(default=None, description="Producing entities responsible for the fonds/document.")
    admin_bio_history: str | None = Field(
        default=None, description="Administrative history or biography of the producer."
    )
    admin_archival_history: str | None = Field(
        default=None, description="Archival history (chain of custody of the document)."
    )
    provenance: str | None = Field(default=None, description="Provenance / origin of the record.")
    scope_content: str | None = Field(
        default=None, description="Scope and content (detailed description of the textual content)."
    )
    language_name: str | None = Field(default=None, description="Predominant language in the descriptive document.")
    archivist_notes: str | None = Field(
        default=None, description="Notes and technical observations of the archivist who cataloged it."
    )
    access_conditions: str | None = Field(
        default=None,
        description="ISAD(G) 4.1: conditions governing access. Parsed by staging and, until this "
        "field existed here, silently dropped by the transfer.",
    )

    # --- ISAD(G), the rest of the record (3.1.5 to 3.7.3) ---
    #: Every one of these was parsed by staging from the beginning and dropped by the transfer, so
    #: the dossier could not show it and the archivist could not correct it.
    dimension_support: str | None = Field(default=None, description="ISAD(G) 3.1.5: extent and medium.")
    appraisal_destruction: str | None = Field(
        default=None, description="ISAD(G) 3.3.2: appraisal, destruction and scheduling."
    )
    accruals: str | None = Field(default=None, description="ISAD(G) 3.3.3: accruals.")
    arrangement: str | None = Field(
        default=None, description="ISAD(G) 3.3.4: the system of arrangement as text, not the position."
    )
    reproduction_conditions: str | None = Field(
        default=None, description="ISAD(G) 3.4.2: conditions governing reproduction."
    )
    physical_characteristics: str | None = Field(
        default=None, description="ISAD(G) 3.4.4: physical characteristics and technical requirements."
    )
    finding_aids: str | None = Field(default=None, description="ISAD(G) 3.4.5: finding aids.")
    originals_location: str | None = Field(
        default=None, description="ISAD(G) 3.5.1: existence and location of the originals."
    )
    copies_location: str | None = Field(default=None, description="ISAD(G) 3.5.2: existence and location of copies.")
    related_units: str | None = Field(default=None, description="ISAD(G) 3.5.3: related units of description.")
    publication_notes: str | None = Field(default=None, description="ISAD(G) 3.5.4: publication note.")
    conservation_notes: str | None = Field(
        default=None, description="The institution's note about the physical state of the record."
    )
    general_notes: str | None = Field(default=None, description="ISAD(G) 3.6.1: general note.")
    rules_conventions: str | None = Field(
        default=None, description="ISAD(G) 3.7.2: rules or conventions the description follows."
    )
    description_dates: str | None = Field(
        default=None, description="ISAD(G) 3.7.3: date(s) of the description, as the source declared them."
    )

    # --- Enrichment (Machine Learning) ---
    final_title: str | None = Field(default=None, description="Title generated by the AI or revised.")

    #: Position in the arrangement, when the source declares one. Both are **optional on purpose**
    #: and they mean "the source said nothing": the INSERT then falls back to the column default (a
    #: root path) and the ON CONFLICT leaves whatever curation placed untouched. Sending them is how
    #: a declared parent wins — which is the whole contract of H6, and the reason the transfer can
    #: no longer be trusted to always speak about the arrangement.
    parent_id: str | None = Field(default=None, description="Parent description, when the source declares one.")
    #: The parent the origin declared, even when it has not arrived yet. It travels beside
    #: ``parent_id`` because the link is not always resolvable at load time.
    parent_reference_code: str | None = Field(
        default=None, description="Reference code of the parent the source declared."
    )
    path: str | None = Field(
        default=None,
        description="Materialised path; omit it and the row is inserted as a root and never re-rooted.",
    )

    execution_log: dict[str, str] = Field(
        default_factory=dict,
        description="Tracks which workers (AI) have already processed the document. E.g.: {'ner_spacy': 'DONE'}",
    )

    # --- Governance (Human-In-The-Loop) ---
    review_status: ArchiveReviewStatus = Field(
        default=ArchiveReviewStatus.PENDING_AI, description="Current audit status."
    )
    is_anomaly: bool = Field(default=False, description="Structural error flag.")
    anomaly_reasons: list[str] | None = Field(default=None, description="List of errors found.")

    model_config = ConfigDict(from_attributes=True)


class DocumentTagSummary(BaseModel):
    """
    Streamlined tag attached to a document when reading the collection.

    It carries the subject decision that travels with the tag — the macro category and the
    confidence the classifier had — because the subject tab has to show *why* a document is
    filed where it is, and reading it from a second route per tag would be an N+1 on the
    front-end. The data already exists on ``ArchiveTag``; this only stops dropping it.
    """

    tag_id: int
    name: str
    macro_category_id: int | None = None
    macro_category_name: str | None = None
    #: ``None`` when the tag never went through the classifier (no subject decision at all).
    ai_confidence_score: float | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentEntitySummary(BaseModel):
    """Streamlined named entity (NER) attached to a document, and who wrote the link."""

    entity_id: int
    name: str
    entity_type: str
    origin: ArchiveEntityOrigin

    model_config = ConfigDict(from_attributes=True)


class FacetCount(BaseModel):
    """
    One selectable value of a facet, with how many documents the current filters leave.

    ``key`` is what the client sends back as the filter value (``typology_id``, ``level_id``,
    ``entity_type``...), kept as a string so every facet can travel in the query string
    unchanged; ``label`` is what a human reads. They differ for every facet whose value is an
    id rather than a name.
    """

    key: str
    label: str
    count: int


class DocumentFacets(BaseModel):
    """
    Counts for the search sidebar, respecting the filters that are active.

    A facet's own selection does **not** constrain its own counts: with "Dossiê" chosen, the
    level list still shows the other rungs and how many documents each would bring. That is
    what makes the sidebar navigable instead of a dead end — the alternative zeroes every
    option except the selected one, and the user can neither widen nor switch.
    """

    typology: list[FacetCount] = Field(default_factory=list)
    macro_category: list[FacetCount] = Field(default_factory=list)
    entity_type: list[FacetCount] = Field(default_factory=list)
    level: list[FacetCount] = Field(default_factory=list)
    #: Why the quality validator flagged the descriptions. It is **curation metadata**, and the
    #: public projection refuses it on purpose (``NOT_PUBLIC_FACETS``): the diffusion surface has no
    #: business publishing how many records are missing a date.
    anomaly_reason: list[FacetCount] = Field(default_factory=list)


class DocumentMacroCategorySummary(BaseModel):
    """Vote of one macro category over the tags of a document."""

    category_id: int
    name: str
    tag_count: int

    model_config = ConfigDict(from_attributes=True)


class DocumentAncestorSummary(BaseModel):
    """
    One rung of the branch a description sits on, root first.

    Streamlined on purpose: the read view of a collection page needs to *place* the description
    ("this item is inside the Série Registros Fotográficos, under the Fundo ALFA"), not to repeat
    the whole ISAD(G) record of every ancestor above it.
    """

    description_id: str
    title: str | None = None
    level: str | None = None


#: The collection's resource and the one sub-route a description advertises for its miniature.
#: They live beside the read view because ``DocumentSummary.thumbnail_url`` *is* that route: a client
#: that assembled the path from an id would be a second definition of a URL the API already declares,
#: and the two would drift in the direction no compiler catches.
DOCUMENTS_RESOURCE = "/api/v1/documents"
THUMBNAIL_SEGMENT = "/{description_id:str}/thumbnail"
_THUMBNAIL_URL_TEMPLATE = DOCUMENTS_RESOURCE + "/{description_id}/thumbnail"


class DocumentSummary(BaseModel):
    """Read view of the collection, consumed by the API and the front-end."""

    description_id: str
    original_title: str
    final_title: str | None = None
    document_date: date | None = None
    review_status: ArchiveReviewStatus
    is_anomaly: bool = False
    anomaly_reasons: list[str] | None = Field(default=None, description="Codes written by the quality validator.")
    #: Derived from the coverage (ADR 0023): the channels that carry the record, and whether any
    #: does. It is a read, not a stored decision — the scopes are the decision — and the approval it
    #: requires is what locks the AI, not the publication.
    is_published: bool = False
    channels: list[str] = Field(default_factory=list, description="Os canais que carregam o registro.")
    storage_thumbnail_uri: str | None = None

    # ISAD(G) fields the archivist may correct; exposed so the API can show what is there.
    reference_code: str | None = None
    #: Name of the catalogue rung. Derived from ``level_id`` on read, kept under the same name
    #: the free-text column used to have so no existing consumer has to change.
    level: str | None = None
    level_id: int | None = None
    #: Typology is a facet of the collection, so the read view has to say which one it is without
    #: the client resolving an id per row.
    typology_id: int | None = None
    typology: str | None = None
    #: Position in the arrangement. ``ancestors`` and ``children_count`` are the H8 surface and
    #: are deliberately not exposed yet: the read view grows when the tree is materialised.
    parent_id: str | None = None
    #: The parent the origin declared, kept even while the link is pending: the dossier can say
    #: "waiting for the parent X" instead of showing an orphan with no explanation.
    parent_reference_code: str | None = None
    path: str | None = None
    producers: str | None = None
    admin_bio_history: str | None = None
    admin_archival_history: str | None = None
    provenance: str | None = None
    scope_content: str | None = None
    language_name: str | None = None
    archivist_notes: str | None = None
    access_conditions: str | None = Field(
        default=None, description="ISAD(G) 4.1: conditions governing access; the diffusion gate."
    )

    #: The date as the source spelled it, and where the record was read from. Both are the record's
    #: evidence and are shown read-only; the description is edited, the source is quoted.
    date_expression: str | None = None
    original_url: str | None = None

    # ISAD(G), the rest of the record. Shown and editable in the dossier's description tab.
    dimension_support: str | None = None
    appraisal_destruction: str | None = None
    accruals: str | None = None
    arrangement: str | None = None
    reproduction_conditions: str | None = None
    physical_characteristics: str | None = None
    finding_aids: str | None = None
    originals_location: str | None = None
    copies_location: str | None = None
    related_units: str | None = None
    publication_notes: str | None = None
    conservation_notes: str | None = None
    general_notes: str | None = None
    rules_conventions: str | None = None
    description_dates: str | None = None

    # Derived on read from the title-scoped excerpts: the machine proposes the title
    # without the repeated fixed part, and only the archivist writes ``final_title``.
    suggested_final_title: str | None = Field(
        default=None, description="Title proposal; never stored, disappears once final_title is written."
    )

    #: The branch this description sits on, root first, read from the materialised path — one
    #: query per page, never one per document.
    ancestors: list[DocumentAncestorSummary] = Field(default_factory=list)
    #: How many descriptions hang directly under this one.
    children_count: int = 0

    tags: list[DocumentTagSummary] = Field(default_factory=list)
    entities: list[DocumentEntitySummary] = Field(default_factory=list)
    # Majority vote over ``tags``: how many of this document's tags belong to each
    # macro category, ordered by count. Built by the repository on read.
    macro_categories: list[DocumentMacroCategorySummary] = Field(default_factory=list)
    # Relevance of a free-text search (higher is better). ``None`` when browsing the
    # collection without a term; the page is always ordered by it when present.
    rank: float | None = Field(default=None, description="Full-text relevance score.")

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        """
        Where the browser reads the miniature, or ``None`` when there is nothing to serve.

        Derived on the server from ``storage_thumbnail_uri`` and **never** assembled by the client:
        the SPA binds this string to an ``<img>``, so it does not know the bucket and cannot drift
        from the route. The bytes themselves come from the authenticated route, which answers 404
        when the object is gone; the screen shows "imagem indisponível" instead of a broken image.

        **An object-backed field is advertised only when ``storage_configured()``.** An installation
        without the four ``S3_*`` settings stores no URI of its own — but a database copied from one
        that had storage still carries them, and advertising those URLs would make a page of
        twenty-five rows issue twenty-five requests for objects this installation cannot read. The
        rule applies to every future object-backed field (#198), not only to this one.
        """
        if not self.storage_thumbnail_uri or not storage_configured():
            return None
        return _THUMBNAIL_URL_TEMPLATE.format(description_id=self.description_id)


class DocumentRevisionDTO(BaseModel):
    """One entry of the human review audit trail (before/after of every changed field)."""

    revision_id: int
    changed_by: str | None = None
    #: ``{"scope_content": {"old": "...", "new": "..."}}``, only the fields that really changed.
    #: Typed with its value and not as a bare ``dict``: a bare one reaches the generated TypeScript
    #: client as ``Record<string, never>``, which the history screen cannot even index.
    changes: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentDeletionDTO(BaseModel):
    """
    One entry of the deletion ledger: what was removed, when, by whom, and the snapshot of it.

    ``snapshot`` is typed as ``dict[str, Any]`` and not as a bare ``dict`` for the reason the revision
    DTO documents: a bare one reaches the generated TypeScript client as ``Record<string, never>``,
    which the ledger screen cannot even index.
    """

    deletion_id: int
    description_id: str
    reference_code: str | None = None
    title: str
    level_name: str | None = None
    children_count: int = 0
    snapshot: dict[str, Any] = Field(default_factory=dict)
    deleted_by: str | None = None
    note: str | None = None
    deleted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentDeletionListResponse(BaseModel):
    """One page of the deletion ledger; ``total`` counts every row matching the search."""

    total: int
    limit: int
    offset: int
    items: list[DocumentDeletionDTO] = Field(default_factory=list)


class DocumentDeletionResponse(RouteResponse):
    """
    The answer to a deletion.

    It carries the ledger entry, not the deleted document: the only thing left to read afterwards is
    the snapshot, and returning it here saves the screen a second request to show what was lost.
    """

    data: DocumentDeletionDTO


class DocumentListResponse(BaseModel):
    """
    Page of collection results.

    ``facets`` always comes back, because a search response that sometimes carries the sidebar
    counts and sometimes does not is a worse contract than one that always does — the client
    would have to know *when* to trust the absence. It costs four grouped queries on an
    indexed set, which is small next to the ranking query it accompanies.
    """

    total: int
    limit: int
    offset: int
    items: list[DocumentSummary]
    facets: DocumentFacets = Field(default_factory=DocumentFacets)

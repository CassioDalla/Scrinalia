"""Output projection of the diffusion surface, shared by every channel.

Security by field omission is fragile; security by an explicit allowlist is auditable. This module
is that allowlist, and it exists so that a field added to the internal read view cannot appear in
public on its own: the projection is built field by field, and a test fails if the public schema
ever grows a field the internal one also has but which was never declared here.

It lives in the domain and not in ``api/schemas`` because the allowlist is not an HTTP detail: the
open dataset (#214) exports the same records, and a domain worker importing the API layer would
invert the dependency. The HTTP module keeps only the page envelope.

The internal ``DocumentSummary`` carries the archive's own process — ``review_status``,
``is_anomaly``, ``anomaly_reasons``, ``archivist_notes``, ``provenance`` and
``suggested_final_title``. Every one of those is a statement about the *curation*, not about the
record, and publishing them would expose the institution's internal work.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from scrinalia.domains.archive.schemas.document_schema import (
    DocumentFacets,
    DocumentSummary,
    FacetCount,
)

#: Fields of ``DocumentSummary`` that are deliberately **not** published. Kept as data, and asserted
#: against the real model by the allowlist test, so the list cannot silently rot: the invariant is
#: an **exact partition** — every field of the internal summary is either published or listed here,
#: and none is in both. Adding a field to the internal read view without classifying it fails CI,
#: which is the point: the default for a new field is "not public".
#:
#: The list mixes three reasons, and each is legitimate:
#:
#: * metadata about the *curation process* — ``review_status``, ``is_anomaly``, ``anomaly_reasons``,
#:   ``archivist_notes``, ``provenance``, ``suggested_final_title``;
#: * machinery and redundancy — ``rank`` (the search score), ``path``/``parent_id`` (the
#:   materialised arrangement), ``level_id``/``typology_id`` (the public reads the resolved *name*
#:   and *code*) and ``is_published`` (every record on this surface is published by construction);
#: * the object-backed field — ``storage_thumbnail_uri`` is an ``s3://bucket/key``, not an address a
#:   browser or a dataset consumer can read; the resolved URL waits for #198;
#: * diffusion still undecided by the product — ``admin_bio_history`` and ``admin_archival_history``
#:   (narrative about people and institutions). Publishing a narrative about a person is a decision
#:   the institution has not taken.
#:
#: The rest of the ISAD(G) block #199 added stays private for the same reason: an appraisal, a
#: location of the originals or a conservation note is an institutional statement the diffusion
#: decision has not reached. ``original_url`` is where the record came from — an external link, not
#: ours to publish.
#:
#: **Widened on 2026-10-30 (#214, ADR 0024)**: ``date_expression``, ``access_conditions`` and
#: ``dimension_support`` left this list, and ``level_code`` joined the projection, because the open
#: dataset is an archival interchange and those are the ISAD(G) fields a consumer needs. The
#: projection is single (ADR 0023), so the public site shows them too; that was the deliberate
#: decision, not a leak.
NOT_PUBLIC_FIELDS = frozenset(
    {
        "review_status",
        "is_anomaly",
        "anomaly_reasons",
        "archivist_notes",
        "provenance",
        "suggested_final_title",
        "rank",
        "path",
        "parent_id",
        "parent_reference_code",
        "level_id",
        "typology_id",
        "is_published",
        "channels",
        "storage_thumbnail_uri",
        "admin_bio_history",
        "admin_archival_history",
        "original_url",
        "appraisal_destruction",
        "accruals",
        "arrangement",
        "reproduction_conditions",
        "physical_characteristics",
        "finding_aids",
        "originals_location",
        "copies_location",
        "related_units",
        "publication_notes",
        "conservation_notes",
        "general_notes",
        "rules_conventions",
        "description_dates",
    }
)


class PublicTagSummary(BaseModel):
    """A subject term as the public sees it: the name, and nothing about how it was decided."""

    tag_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class PublicEntitySummary(BaseModel):
    """A named entity as the public sees it."""

    entity_id: int
    name: str
    entity_type: str

    model_config = ConfigDict(from_attributes=True)


class PublicMacroCategorySummary(BaseModel):
    """How many of the document's terms belong to each subject drawer."""

    category_id: int
    name: str
    #: Kept because the public badge rule reads it: without the counts a card cannot show
    #: ``[ Urbanismo ] [+1]``, and that rule is the whole point of the vote being computed.
    tag_count: int

    model_config = ConfigDict(from_attributes=True)


class PublicAncestorSummary(BaseModel):
    """One rung of the branch the description sits on, root first."""

    description_id: str
    title: str | None = None
    level: str | None = None
    #: The rung's stable catalogue key; ``level`` is the label the archivist may rename.
    level_code: str | None = None


class PublicDocumentSummary(BaseModel):
    """
    What the diffusion site is allowed to show about one description.

    Built by :meth:`from_summary`, never by ``model_validate`` on the internal DTO: validating the
    internal object would make every field it gains automatically public, which is exactly the
    failure this class exists to prevent.

    ``extra="forbid"`` makes the generated JSON Schema say the same thing the class does: this is the
    complete set of fields, not an open object. The dataset contract (ADR 0024) is generated from it.
    """

    model_config = ConfigDict(extra="forbid")

    description_id: str
    original_title: str
    final_title: str | None = None
    document_date: date | None = None
    #: ISAD(G) 3.1.3 as the source spelled it ("1910-1950"). The normalized ``document_date`` stays
    #: the machine date; this is the quotation a finding aid shows.
    date_expression: str | None = None

    # --- ISAD(G) ---
    reference_code: str | None = None
    #: ISAD(G) 3.1.4. ``level`` is the editable catalogue name; ``level_code`` is the stable key an
    #: export groups by. Both are published for that reason.
    level: str | None = None
    level_code: str | None = None
    #: ISAD(G) 3.1.5: extent and medium ("papel; 30 x 21 cm").
    dimension_support: str | None = None
    scope_content: str | None = None
    language_name: str | None = None
    #: ISAD(G) 3.2.1: who produced the record. Core descriptive metadata and the reason a diffusion
    #: site is useful at all, so it is published; ``provenance`` and ``admin_*_history``, which
    #: narrate the chain of custody and people's lives, are not.
    producers: str | None = None
    #: ISAD(G) 4.1: the conditions governing access. Descriptive, not the gate: the gate is the
    #: channel coverage, and a record that is covered is approved and public.
    access_conditions: str | None = None

    # --- Enrichment that describes the record, not the process ---
    typology: str | None = None
    tags: list[PublicTagSummary] = Field(default_factory=list)
    entities: list[PublicEntitySummary] = Field(default_factory=list)
    macro_categories: list[PublicMacroCategorySummary] = Field(default_factory=list)

    #: The branch, root first: a public description has to be placeable in its fonds.
    ancestors: list[PublicAncestorSummary] = Field(default_factory=list)
    children_count: int = 0

    @classmethod
    def from_summary(cls, summary: DocumentSummary) -> "PublicDocumentSummary":
        """Projects the internal read view onto the allowlist, field by field and on purpose."""
        return cls(
            description_id=summary.description_id,
            original_title=summary.original_title,
            final_title=summary.final_title,
            document_date=summary.document_date,
            date_expression=summary.date_expression,
            reference_code=summary.reference_code,
            level=summary.level,
            level_code=summary.level_code,
            dimension_support=summary.dimension_support,
            scope_content=summary.scope_content,
            language_name=summary.language_name,
            producers=summary.producers,
            access_conditions=summary.access_conditions,
            typology=summary.typology,
            tags=[PublicTagSummary(tag_id=tag.tag_id, name=tag.name) for tag in summary.tags],
            entities=[
                PublicEntitySummary(entity_id=entity.entity_id, name=entity.name, entity_type=entity.entity_type)
                for entity in summary.entities
            ],
            macro_categories=[
                PublicMacroCategorySummary(
                    category_id=category.category_id, name=category.name, tag_count=category.tag_count
                )
                for category in summary.macro_categories
            ],
            ancestors=[
                PublicAncestorSummary(
                    description_id=ancestor.description_id,
                    title=ancestor.title,
                    level=ancestor.level,
                    level_code=ancestor.level_code,
                )
                for ancestor in summary.ancestors
            ],
            children_count=summary.children_count,
        )


#: Facet dimensions the diffusion surface must never publish, as an **exact partition** of
#: ``DocumentFacets`` — the same rule ``NOT_PUBLIC_FIELDS`` applies to the summary, and for the same
#: reason. Sharing the internal envelope meant that adding a dimension to ``DocumentFacets``
#: published it automatically, which is how the anomaly counts would have reached the public site:
#: "how many records are missing a date" is curation metadata, not a description of the collection.
NOT_PUBLIC_FACETS = frozenset({"anomaly_reason"})


class PublicDocumentFacets(BaseModel):
    """
    The sidebar of the diffusion surface, built **field by field** from the internal one.

    Not ``model_validate``: validating the internal object would make every dimension it gains
    automatically public, which is exactly the failure ``NOT_PUBLIC_FIELDS`` exists to prevent on the
    summary side. The four dimensions here are the ones the public route already accepts as filters,
    so a visitor can widen the search along an axis the sidebar offers.
    """

    typology: list[FacetCount] = Field(default_factory=list)
    macro_category: list[FacetCount] = Field(default_factory=list)
    entity_type: list[FacetCount] = Field(default_factory=list)
    level: list[FacetCount] = Field(default_factory=list)

    @classmethod
    def from_facets(cls, facets: DocumentFacets) -> "PublicDocumentFacets":
        """Narrows the internal envelope to the published dimensions."""
        return cls(
            typology=facets.typology,
            macro_category=facets.macro_category,
            entity_type=facets.entity_type,
            level=facets.level,
        )

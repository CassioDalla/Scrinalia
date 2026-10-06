"""The diffusion allowlist, and the guarantee that it cannot rot silently.

``DocumentSummary`` carries the archive's internal process, and the public surface must not. The
roadmap's argument is that security by *field omission* is fragile while security by an explicit
allowlist is auditable — this module is that audit, made executable.
"""

from datetime import date

import pytest

from memoria_curitibana.api.schemas.public import (
    NOT_PUBLIC_FACETS,
    NOT_PUBLIC_FIELDS,
    PublicDocumentFacets,
    PublicDocumentSummary,
)
from memoria_curitibana.domains.archive.models import ArchiveReviewStatus
from memoria_curitibana.domains.archive.schemas.document_schema import (
    DocumentAncestorSummary,
    DocumentEntitySummary,
    DocumentFacets,
    DocumentMacroCategorySummary,
    DocumentSummary,
    DocumentTagSummary,
    FacetCount,
)


def _internal_summary() -> DocumentSummary:
    return DocumentSummary(
        description_id="doc-1",
        original_title="Título",
        final_title=None,
        document_date=date(1954, 3, 12),
        review_status=ArchiveReviewStatus.NEEDS_REVIEW,
        is_anomaly=True,
        anomaly_reasons=["BAD_DATE"],
        is_published=True,
        storage_thumbnail_uri="s3://thumb.jpg",
        reference_code="BR PR",
        level="Dossiê",
        level_id=5,
        typology_id=9,
        typology="Fotografia",
        parent_id="serie",
        path="acervo.serie.doc-1",
        producers="IPPUC",
        admin_bio_history="história sigilosa",
        admin_archival_history="custódia interna",
        provenance="doação",
        scope_content="Conteúdo",
        language_name="pt-BR",
        archivist_notes="nota interna",
        access_conditions="consulta mediante autorização",
        suggested_final_title="Título sugerido",
        ancestors=[DocumentAncestorSummary(description_id="serie", title="Série", level="Série")],
        children_count=2,
        tags=[DocumentTagSummary(tag_id=1, name="urbanismo", macro_category_id=4, macro_category_name="Urbanismo")],
        entities=[DocumentEntitySummary(entity_id=2, name="Curitiba", entity_type="LOC")],
        macro_categories=[DocumentMacroCategorySummary(category_id=4, name="Urbanismo", tag_count=1)],
        rank=0.75,
    )


def test_every_internal_field_is_classified() -> None:
    """
    The allowlist is an exact partition of the internal read view.

    This is the test the roadmap asked for, stated in its strongest form. It is not "the public
    schema has these fields" — such a test stays green when someone adds an internal field and the
    public schema picks it up. It asserts the *complement*: every field of ``DocumentSummary`` is
    either published or explicitly refused, so a new field defaults to private and CI says so.
    """
    internal = set(DocumentSummary.model_fields)
    published = set(PublicDocumentSummary.model_fields)

    unclassified = internal - published - NOT_PUBLIC_FIELDS
    assert not unclassified, (
        f"Campos novos em DocumentSummary sem decisão de difusão: {sorted(unclassified)}. "
        "Publique-o em PublicDocumentSummary ou declare-o em NOT_PUBLIC_FIELDS."
    )

    both = published & NOT_PUBLIC_FIELDS
    assert not both, f"Campos declarados como não públicos e expostos ao mesmo tempo: {sorted(both)}"


def test_no_public_field_is_invented() -> None:
    """The projection may only narrow the internal view, never add a field the domain does not have."""
    invented = set(PublicDocumentSummary.model_fields) - set(DocumentSummary.model_fields)
    assert not invented, f"Campos públicos sem origem no domínio: {sorted(invented)}"


@pytest.mark.parametrize(
    "field",
    [
        "review_status",
        "is_anomaly",
        "anomaly_reasons",
        "archivist_notes",
        "provenance",
        "suggested_final_title",
        "access_conditions",
        "admin_bio_history",
        "admin_archival_history",
    ],
)
def test_the_projection_drops_the_internal_metadata(field: str) -> None:
    """Each field named in the ADR is actually absent from what a public client receives."""
    projected = PublicDocumentSummary.from_summary(_internal_summary())
    assert field not in projected.model_dump()


def test_the_projection_keeps_what_describes_the_record() -> None:
    """The allowlist must not be so tight that it stops being an archival description."""
    projected = PublicDocumentSummary.from_summary(_internal_summary())

    assert projected.description_id == "doc-1"
    assert projected.typology == "Fotografia"
    assert projected.producers == "IPPUC"
    assert [tag.name for tag in projected.tags] == ["urbanismo"]
    # The tag loses the subject decision; the drawer still arrives as its own list.
    assert "macro_category_name" not in projected.tags[0].model_dump()
    assert [(category.name, category.tag_count) for category in projected.macro_categories] == [("Urbanismo", 1)]
    assert [ancestor.description_id for ancestor in projected.ancestors] == ["serie"]
    assert projected.children_count == 2


# ==========================================
# THE FACET ENVELOPE: THE SAME RULE, ONE LEVEL UP
# ==========================================


def test_every_internal_facet_is_classified() -> None:
    """
    The facet allowlist is an exact partition too, and it was not one before.

    The public list response shared ``DocumentFacets`` with the internal search, so adding a
    dimension to the internal envelope published it automatically — which is how the anomaly counts
    would have reached the diffusion surface. A new dimension now defaults to private and CI says so.
    """
    internal = set(DocumentFacets.model_fields)
    published = set(PublicDocumentFacets.model_fields)

    unclassified = internal - published - NOT_PUBLIC_FACETS
    assert not unclassified, (
        f"Dimensões novas em DocumentFacets sem decisão de difusão: {sorted(unclassified)}. "
        "Publique-a em PublicDocumentFacets ou declare-a em NOT_PUBLIC_FACETS."
    )

    both = published & NOT_PUBLIC_FACETS
    assert not both, f"Dimensões declaradas como não públicas e expostas ao mesmo tempo: {sorted(both)}"


def test_no_public_facet_is_invented() -> None:
    """The projection narrows the internal envelope; it never adds a dimension the search lacks."""
    invented = set(PublicDocumentFacets.model_fields) - set(DocumentFacets.model_fields)
    assert not invented, f"Dimensões públicas sem origem no domínio: {sorted(invented)}"


def test_the_anomaly_counts_never_reach_the_diffusion_surface() -> None:
    """
    "How many records are missing a date" is curation metadata, not a description of the collection.

    The internal envelope carries the counts; the projection drops them and keeps the four axes the
    public route already accepts as filters.
    """
    internal = DocumentFacets(
        typology=[FacetCount(key="1", label="Fotografia", count=3)],
        anomaly_reason=[FacetCount(key="MISSING_DATE", label="MISSING_DATE", count=41)],
    )

    projected = PublicDocumentFacets.from_facets(internal)

    assert "anomaly_reason" not in projected.model_dump()
    assert [(item.label, item.count) for item in projected.typology] == [("Fotografia", 3)]
    assert projected.macro_category == []
    assert projected.entity_type == []
    assert projected.level == []

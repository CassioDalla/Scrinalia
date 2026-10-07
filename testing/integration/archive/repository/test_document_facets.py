"""The search sidebar counts, and the rule that makes it navigable.

The property under test is the one that is easy to get wrong and invisible until a user is stuck:
**a facet's own selection must not constrain its own counts**. Counting under the applied filter
zeroes every other option, so the archivist can neither widen the search nor switch rung.
"""

from scrinalia.domains.archive.models import (
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveMacroCategory,
    ArchiveTag,
    ArchiveTypology,
)
from scrinalia.domains.archive.repository.document_repo import DocumentRepository
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery

# ==========================================
# SEARCH FACETS
# ==========================================


def test_facets_count_by_typology_level_and_subject(db_session, generate_archive_doc, generate_typology):
    photo = generate_typology(id=1, name="Fotografia")
    plan = generate_typology(id=2, name="Planta")
    drawer = ArchiveMacroCategory(category_id=7, name="Urbanismo")
    db_session.add(drawer)
    db_session.flush()
    tag = ArchiveTag(name="urbanismo", macro_category_id=7)
    db_session.add(tag)
    db_session.flush()

    first = generate_archive_doc(description_id="f1", original_title="Foto 1", typology_id=photo.typology_id)
    second = generate_archive_doc(description_id="f2", original_title="Foto 2", typology_id=photo.typology_id)
    generate_archive_doc(description_id="p1", original_title="Planta 1", typology_id=plan.typology_id)
    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=first.description_id, tag_id=tag.tag_id),
            ArchiveDocumentTag(description_id=second.description_id, tag_id=tag.tag_id),
        ]
    )
    db_session.flush()

    _, total, facets = DocumentRepository(db_session).search(DocumentSearchQuery())

    assert total == 3
    assert {(item.key, item.count) for item in facets.typology} == {("1", 2), ("2", 1)}
    assert {(item.key, item.label, item.count) for item in facets.macro_category} == {("7", "Urbanismo", 2)}


def test_a_selected_facet_does_not_zero_its_own_options(db_session, generate_archive_doc, generate_typology):
    """
    With "Fotografia" applied, the typology list still offers "Planta".

    This is the difference between a sidebar and a dead end: the count of the option you are *not*
    on is what lets you switch to it.
    """
    photo = generate_typology(id=1, name="Fotografia")
    plan = generate_typology(id=2, name="Planta")
    generate_archive_doc(description_id="f1", original_title="Foto 1", typology_id=photo.typology_id)
    generate_archive_doc(description_id="p1", original_title="Planta 1", typology_id=plan.typology_id)
    db_session.flush()

    docs, total, facets = DocumentRepository(db_session).search(DocumentSearchQuery(typology_id=photo.typology_id))

    assert total == 1
    assert [doc.description_id for doc in docs] == ["f1"]
    # The page is filtered, the facet is not: "Planta" survives with its own count.
    assert {(item.key, item.count) for item in facets.typology} == {("1", 1), ("2", 1)}


def test_another_facet_still_filters_the_selected_one(db_session, generate_archive_doc, generate_typology):
    """
    Only the dimension's *own* filter is lifted.

    A date range, a subject drawer or the search term must still narrow every list — otherwise the
    sidebar would describe a collection the user is not looking at.
    """
    photo = generate_typology(id=1, name="Fotografia")
    plan = generate_typology(id=2, name="Planta")
    drawer = ArchiveMacroCategory(category_id=7, name="Urbanismo")
    other = ArchiveMacroCategory(category_id=8, name="Saúde")
    db_session.add_all([drawer, other])
    db_session.flush()
    urban = ArchiveTag(name="urbanismo", macro_category_id=7)
    health = ArchiveTag(name="saude", macro_category_id=8)
    db_session.add_all([urban, health])
    db_session.flush()

    photo_doc = generate_archive_doc(description_id="f1", original_title="Foto", typology_id=photo.typology_id)
    plan_doc = generate_archive_doc(description_id="p1", original_title="Planta", typology_id=plan.typology_id)
    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=photo_doc.description_id, tag_id=urban.tag_id),
            ArchiveDocumentTag(description_id=plan_doc.description_id, tag_id=health.tag_id),
        ]
    )
    db_session.flush()

    _, _, facets = DocumentRepository(db_session).search(DocumentSearchQuery(macro_category_id=7))

    # Filtered by "Urbanismo", the typology list has to show only what is inside it.
    assert [(item.key, item.count) for item in facets.typology] == [("1", 1)]
    # ...while the subject list, whose own filter is the one being lifted, still offers the other
    # drawer with the single document it would bring — which is what lets the user switch to it.
    assert {(item.label, item.count) for item in facets.macro_category} == {("Urbanismo", 1), ("Saúde", 1)}


def test_entity_type_facet_counts_documents_not_links(db_session, generate_archive_doc):
    """A document with three ORG entities is one document in the ORG count, not three."""
    org_a = ArchiveEntity(name="Prefeitura", entity_type="ORG")
    org_b = ArchiveEntity(name="URBS", entity_type="ORG")
    org_c = ArchiveEntity(name="IPPUC", entity_type="ORG")
    place = ArchiveEntity(name="Curitiba", entity_type="LOC")
    db_session.add_all([org_a, org_b, org_c, place])
    db_session.flush()

    doc = generate_archive_doc(description_id="d1", original_title="Documento")
    other = generate_archive_doc(description_id="d2", original_title="Outro")
    db_session.add_all(
        [
            ArchiveDocumentEntity(description_id=doc.description_id, entity_id=org_a.entity_id),
            ArchiveDocumentEntity(description_id=doc.description_id, entity_id=org_b.entity_id),
            ArchiveDocumentEntity(description_id=doc.description_id, entity_id=org_c.entity_id),
            ArchiveDocumentEntity(description_id=other.description_id, entity_id=place.entity_id),
        ]
    )
    db_session.flush()

    _, _, facets = DocumentRepository(db_session).search(DocumentSearchQuery())

    assert {(item.key, item.count) for item in facets.entity_type} == {("ORG", 1), ("LOC", 1)}


def test_the_facets_describe_the_term_the_page_came_from(db_session, generate_archive_doc):
    """
    The counts follow the search term, not the whole collection.

    A sidebar that ignored the term would keep offering 3 608 documents while the page shows two.
    """
    generate_archive_doc(description_id="d1", original_title="Matadouro Municipal")
    generate_archive_doc(description_id="d2", original_title="Matadouro Novo")
    generate_archive_doc(description_id="d3", original_title="Praça Central")
    db_session.flush()

    docs, total, _ = DocumentRepository(db_session).search(DocumentSearchQuery(term="matadouro"))

    assert total == 2
    assert {doc.description_id for doc in docs} == {"d1", "d2"}


def test_facets_are_empty_when_nothing_matches(db_session, generate_archive_doc, generate_typology):
    """No results means no options; the UI shows the empty state, not a stale sidebar."""
    typology = generate_typology(id=1, name="Fotografia")
    generate_archive_doc(description_id="d1", original_title="Documento", typology_id=typology.typology_id)
    db_session.flush()

    docs, total, facets = DocumentRepository(db_session).search(DocumentSearchQuery(term="zznada"))

    assert (docs, total) == ([], 0)
    assert facets.typology == []


def test_typology_facet_ignores_documents_without_a_typology(db_session, generate_archive_doc, generate_typology):
    """An unclassified document is not a typology; it simply does not appear in that list."""
    typology = ArchiveTypology(typology_id=1, name="Fotografia")
    db_session.add(typology)
    db_session.flush()
    generate_archive_doc(description_id="d1", original_title="Classificado", typology_id=1)
    generate_archive_doc(description_id="d2", original_title="Sem tipologia")
    db_session.flush()

    _, total, facets = DocumentRepository(db_session).search(DocumentSearchQuery())

    assert total == 2
    assert [(item.key, item.count) for item in facets.typology] == [("1", 1)]


# ==========================================
# ANOMALY REASONS: A FACET OVER A MIXED COLUMN
# ==========================================


def _flag(db_session, doc, reasons: list[str]) -> None:
    """Writes the two columns the validator writes, so the fixture matches production."""
    doc.anomaly_reasons = reasons
    doc.is_anomaly = bool(reasons)
    db_session.flush()


def test_the_anomaly_facet_groups_by_code_and_names_the_rule(db_session, generate_archive_doc):
    """
    ``anomaly_reasons`` mixes a stable code with an optional payload, and the bucket is the code.

    ``RULE_MATCH`` is the exception: the rule's name *is* the payload, and a rule is a catalogue
    entry the archivist maintains — "which rule flagged this?" is the question the screen exists to
    answer. So that one keeps its payload in the key.
    """
    first = generate_archive_doc(description_id="a1", original_title="Sem data")
    second = generate_archive_doc(description_id="a2", original_title="Sem tags")
    third = generate_archive_doc(description_id="a3", original_title="Tudo junto")

    _flag(db_session, first, ["MISSING_DATE"])
    _flag(db_session, second, ["NO_TAGS", "RULE_MATCH:data fora do intervalo"])
    _flag(db_session, third, ["MISSING_DATE", "NO_TAGS", "RULE_MATCH:data fora do intervalo"])

    _, total, facets = DocumentRepository(db_session).search(DocumentSearchQuery())

    assert total == 3
    assert {(item.key, item.count) for item in facets.anomaly_reason} == {
        ("MISSING_DATE", 2),
        ("NO_TAGS", 2),
        ("RULE_MATCH:data fora do intervalo", 2),
    }


def test_the_free_text_of_an_llm_check_collapses_to_its_code(db_session, generate_archive_doc):
    """
    A facet over the model's prose would be a long tail of buckets that never repeat.

    ``LLM_SUSPECT:<reason>`` carries free text the model wrote about one title, so the bucket is the
    code: the archivist filters "the model found this suspicious" and reads the text on the card.
    """
    first = generate_archive_doc(description_id="l1", original_title="A")
    second = generate_archive_doc(description_id="l2", original_title="B")
    _flag(db_session, first, ["LLM_SUSPECT:título genérico demais"])
    _flag(db_session, second, ["LLM_SUSPECT:parece um boilerplate de origem"])

    _, _, facets = DocumentRepository(db_session).search(DocumentSearchQuery())

    assert {(item.key, item.count) for item in facets.anomaly_reason} == {("LLM_SUSPECT", 2)}


def test_selecting_a_reason_does_not_zero_its_own_options(db_session, generate_archive_doc):
    """The sidebar rule holds for the new dimension too, or the filter is a dead end."""
    first = generate_archive_doc(description_id="r1", original_title="A")
    second = generate_archive_doc(description_id="r2", original_title="B")
    _flag(db_session, first, ["MISSING_DATE"])
    _flag(db_session, second, ["NO_TAGS"])

    _, total, facets = DocumentRepository(db_session).search(DocumentSearchQuery(anomaly_reason="MISSING_DATE"))

    assert total == 1
    # Both buckets still show: the archivist can switch to the other reason without clearing first.
    assert {(item.key, item.count) for item in facets.anomaly_reason} == {("MISSING_DATE", 1), ("NO_TAGS", 1)}


def test_the_reason_filter_accepts_the_key_the_facet_shows(db_session, generate_archive_doc):
    """
    The key the sidebar offers is a key the route accepts.

    The filter and the facet share one expression for the bucket, so a screen cannot render a bucket
    the search refuses — which is what a hand-written ``split_part`` in either place would allow.
    """
    first = generate_archive_doc(description_id="k1", original_title="A")
    second = generate_archive_doc(description_id="k2", original_title="B")
    third = generate_archive_doc(description_id="k3", original_title="C")
    _flag(db_session, first, ["RULE_MATCH:data fora do intervalo"])
    _flag(db_session, second, ["RULE_MATCH:outra regra"])
    _flag(db_session, third, ["MISSING_DATE"])

    _, total, facets = DocumentRepository(db_session).search(
        DocumentSearchQuery(anomaly_reason="RULE_MATCH:data fora do intervalo")
    )

    assert total == 1
    assert {item.key for item in facets.anomaly_reason} == {
        "RULE_MATCH:data fora do intervalo",
        "RULE_MATCH:outra regra",
        "MISSING_DATE",
    }


def test_documents_without_reasons_are_not_counted(db_session, generate_archive_doc):
    """A clean description belongs to no bucket — ``NULL`` is not a reason."""
    generate_archive_doc(description_id="c1", original_title="Limpa")
    flagged = generate_archive_doc(description_id="c2", original_title="Marcada")
    _flag(db_session, flagged, ["NO_ENTITIES"])

    _, total, facets = DocumentRepository(db_session).search(DocumentSearchQuery())

    assert total == 2
    assert {(item.key, item.count) for item in facets.anomaly_reason} == {("NO_ENTITIES", 1)}

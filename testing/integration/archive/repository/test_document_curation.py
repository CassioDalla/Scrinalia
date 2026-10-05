"""Integration tests of the human curation surface (real PostgreSQL)."""

from datetime import date

import pytest
from sqlalchemy import select

from memoria_curitibana.domains.archive.exceptions import EntityNotFoundError, TagNotFoundError
from memoria_curitibana.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentRevision,
    ArchiveEntity,
    ArchiveReviewStatus,
    ArchiveTag,
)
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    apply_excerpts_in_python,
    effective_column_sql,
)
from memoria_curitibana.domains.archive.schemas.command_schema import (
    DocumentReviewCommand,
    EntityLinkCommand,
    TagLinkCommand,
)
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery
from memoria_curitibana.domains.archive.schemas.text_quality_schema import TemplateCreateCommand, TemplateUpdateCommand


def _title_template(db_session, text: str = "Registros Fotográficos -") -> None:
    TextQualityRepository(db_session).create_template(TemplateCreateCommand(text=text, scope=["TITLE"]))
    db_session.flush()


# ==========================================
# AUDIT TRAIL
# ==========================================


def test_update_review_can_fix_any_isad_g_field(db_session, generate_archive_doc, generate_description_level) -> None:
    generate_archive_doc(description_id="edit-1", original_title="Título antigo")
    level = generate_description_level(ordinal=5, code="item", name="Item Documental")

    summary = DocumentRepository(db_session).update_review(
        DocumentReviewCommand(
            description_id="edit-1",
            document_date=date(1954, 3, 15),
            reference_code="BR PR IPPUC",
            level_id=level.level_id,
            producers="IPPUC",
            provenance="IPPUC",
            language_name="pt-BR",
            admin_archival_history="Transferido em 1999.",
            changed_by="ana",
        )
    )

    assert summary is not None
    assert summary.reference_code == "BR PR IPPUC"
    assert summary.document_date == date(1954, 3, 15)


def test_update_review_records_only_what_changed(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="edit-2", original_title="Título antigo", scope_content="Escopo")

    DocumentRepository(db_session).update_review(
        DocumentReviewCommand(
            description_id="edit-2",
            original_title="Título corrigido",
            scope_content="Escopo",  # identical: must not appear in the trail
            changed_by="ana",
            review_note="Correção do título",
        )
    )

    revisions = DocumentRepository(db_session).list_revisions("edit-2")
    assert len(revisions) == 1
    assert list(revisions[0].changes) == ["original_title"]
    assert revisions[0].changes["original_title"] == {"old": "Título antigo", "new": "Título corrigido"}
    assert revisions[0].changed_by == "ana"
    assert revisions[0].note == "Correção do título"


def test_update_review_without_changes_writes_no_revision(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="edit-3", original_title="Título")

    DocumentRepository(db_session).update_review(
        DocumentReviewCommand(description_id="edit-3", original_title="Título")
    )

    assert DocumentRepository(db_session).list_revisions("edit-3") == []


def test_update_review_records_a_date_as_text(db_session, generate_archive_doc) -> None:
    """The JSONB trail must be serializable: dates travel as ISO strings."""
    generate_archive_doc(description_id="edit-4", document_date=date(1950, 1, 1))

    DocumentRepository(db_session).update_review(
        DocumentReviewCommand(description_id="edit-4", document_date=date(1954, 3, 15), changed_by="ana")
    )

    revision = DocumentRepository(db_session).list_revisions("edit-4")[0]
    assert revision.changes["document_date"] == {"old": "1950-01-01", "new": "1954-03-15"}


def test_list_revisions_is_newest_first(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="edit-5", original_title="A")
    repository = DocumentRepository(db_session)

    repository.update_review(DocumentReviewCommand(description_id="edit-5", original_title="B", changed_by="ana"))
    repository.update_review(DocumentReviewCommand(description_id="edit-5", original_title="C", changed_by="bruno"))

    revisions = repository.list_revisions("edit-5")
    assert [revision.changes["original_title"]["new"] for revision in revisions] == ["C", "B"]
    assert [revision.changed_by for revision in revisions] == ["bruno", "ana"]


def test_update_review_marks_the_document_human_approved(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="edit-6", original_title="A")

    summary = DocumentRepository(db_session).update_review(
        DocumentReviewCommand(description_id="edit-6", final_title="Título do arquivista", changed_by="ana")
    )

    assert summary.review_status == "HUMAN_APPROVED"


def test_revisions_cascade_with_the_document(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="edit-7", original_title="A")
    repository = DocumentRepository(db_session)
    repository.update_review(DocumentReviewCommand(description_id="edit-7", original_title="B", changed_by="ana"))

    doc = db_session.get(ArchiveDocument, "edit-7")
    db_session.delete(doc)
    db_session.flush()

    assert db_session.scalars(select(ArchiveDocumentRevision)).all() == []


# ==========================================
# SUGGESTED TITLE
# ==========================================


def test_suggested_final_title_strips_the_approved_template(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="title-1", original_title="Registros Fotográficos - Rua Izaac Ferreira")
    _title_template(db_session)

    summary = DocumentRepository(db_session).get_by_id("title-1")

    assert summary.suggested_final_title == "Rua Izaac Ferreira"
    assert summary.original_title == "Registros Fotográficos - Rua Izaac Ferreira"


def test_suggested_final_title_needs_an_approved_template(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="title-2", original_title="Registros Fotográficos - Rua Izaac")

    assert DocumentRepository(db_session).get_by_id("title-2").suggested_final_title is None


def test_a_pending_title_excerpt_is_not_applied(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="title-3", original_title="Registros Fotográficos - Rua Izaac")
    repository = TextQualityRepository(db_session)
    template = repository.create_template(TemplateCreateCommand(text="Registros Fotográficos -", scope=["TITLE"]))
    repository.update_template(template.template_id, TemplateUpdateCommand(status="SUGGESTED", is_active=False))
    db_session.flush()

    assert DocumentRepository(db_session).get_by_id("title-3").suggested_final_title is None


def test_suggested_final_title_disappears_once_the_human_decides(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="title-4", original_title="Registros Fotográficos - Rua Izaac")
    _title_template(db_session)

    summary = DocumentRepository(db_session).update_review(
        DocumentReviewCommand(description_id="title-4", final_title="Rua Izaac", changed_by="ana")
    )

    assert summary.final_title == "Rua Izaac"
    assert summary.suggested_final_title is None


def test_a_general_excerpt_does_not_become_a_title_suggestion(db_session, generate_archive_doc) -> None:
    """Scope is respected: an EMBEDDING excerpt must not rewrite the proposed title."""
    generate_archive_doc(description_id="title-5", original_title="Rua Izaac", scope_content="Bloco repetido do acervo")
    TextQualityRepository(db_session).create_template(
        TemplateCreateCommand(text="Bloco repetido do acervo", scope=["EMBEDDING", "NER"])
    )
    db_session.flush()

    assert DocumentRepository(db_session).get_by_id("title-5").suggested_final_title is None


# ==========================================
# THE PYTHON MIRROR AND THE SQL EXPRESSION
# ==========================================


def test_python_and_sql_apply_the_same_excerpts(db_session, generate_archive_doc) -> None:
    """``_suggest_title`` reads in Python; the workers compose in SQL. They must agree."""
    raw = "Registros   Fotográficos  -  Rua Izaac,  1954"
    doc = generate_archive_doc(description_id="parity-1", original_title=raw)
    _title_template(db_session, text="Registros Fotográficos -")
    rules = TextQualityRepository(db_session).get_active_rules("TITLE")

    sql_value = db_session.scalar(
        select(effective_column_sql("original_title", rules)).where(
            ArchiveDocument.description_id == doc.description_id
        )
    )

    assert apply_excerpts_in_python(raw, rules) == sql_value


# ==========================================
# LOCAL SUBJECT CURATION (tags / entities of ONE description)
# ==========================================
#
# Until this existed, "this document is about this too" could only be decided by merging terms
# globally or by re-running a worker. The decision now happens where the archivist reads it.


def _tag(db_session, name: str = "urbanismo", **kwargs) -> ArchiveTag:
    tag = ArchiveTag(name=name, **kwargs)
    db_session.add(tag)
    db_session.flush()
    return tag


def _entity(db_session, name: str = "Curitiba", entity_type: str = "LOC") -> ArchiveEntity:
    entity = ArchiveEntity(name=name, entity_type=entity_type)
    db_session.add(entity)
    db_session.flush()
    return entity


def test_linking_a_tag_records_the_revision_and_approves_the_document(db_session, generate_archive_doc) -> None:
    """The whole point of the flow: the decision is written down and the AI is locked out."""
    tag = _tag(db_session)
    generate_archive_doc(description_id="tag-1", original_title="Documento")

    summary = DocumentRepository(db_session).link_tag(
        TagLinkCommand(description_id="tag-1", tag_id=tag.tag_id), changed_by="ana", note="assunto claro"
    )

    assert summary is not None
    assert [item.name for item in summary.tags] == ["urbanismo"]
    assert summary.review_status == ArchiveReviewStatus.HUMAN_APPROVED

    revisions = DocumentRepository(db_session).list_revisions("tag-1")
    assert len(revisions) == 1
    assert revisions[0].changed_by == "ana"
    assert revisions[0].note == "assunto claro"
    assert revisions[0].changes == {"tags": {"old": [], "new": ["urbanismo"]}}


def test_unlinking_a_tag_records_the_names_on_both_sides(db_session, generate_archive_doc) -> None:
    """
    The ledger stores the whole list of names, not a diff of ids.

    "Which terms did this description carry" is the decision; an id would not survive a rename and
    would make the revision unreadable a year later.
    """
    first = _tag(db_session, name="urbanismo")
    second = _tag(db_session, name="alvenaria")
    generate_archive_doc(description_id="tag-2", original_title="Documento")
    repository = DocumentRepository(db_session)
    repository.link_tag(TagLinkCommand(description_id="tag-2", tag_id=first.tag_id))
    repository.link_tag(TagLinkCommand(description_id="tag-2", tag_id=second.tag_id))

    repository.unlink_tag(TagLinkCommand(description_id="tag-2", tag_id=first.tag_id), changed_by="bia")

    revision = repository.list_revisions("tag-2")[0]
    assert revision.changes == {"tags": {"old": ["alvenaria", "urbanismo"], "new": ["alvenaria"]}}
    assert revision.changed_by == "bia"


def test_linking_the_same_tag_twice_does_not_duplicate_it_or_the_revision(db_session, generate_archive_doc) -> None:
    """A repeated click is idempotent on the data; there is nothing new to explain the second time."""
    tag = _tag(db_session)
    generate_archive_doc(description_id="tag-3", original_title="Documento")
    repository = DocumentRepository(db_session)

    repository.link_tag(TagLinkCommand(description_id="tag-3", tag_id=tag.tag_id))
    summary = repository.link_tag(TagLinkCommand(description_id="tag-3", tag_id=tag.tag_id))

    assert summary is not None
    assert len(summary.tags) == 1
    assert len(repository.list_revisions("tag-3")) == 1


def test_linking_a_tag_that_does_not_exist_is_a_business_error(db_session, generate_archive_doc) -> None:
    """The id comes from a client; a stale one must be a named 404, not an integrity error."""
    generate_archive_doc(description_id="tag-4", original_title="Documento")

    with pytest.raises(TagNotFoundError):
        DocumentRepository(db_session).link_tag(TagLinkCommand(description_id="tag-4", tag_id=99999))


def test_unlinking_a_tag_the_document_does_not_have_is_a_business_error(db_session, generate_archive_doc) -> None:
    tag = _tag(db_session, name="orfa")
    generate_archive_doc(description_id="tag-5", original_title="Documento")

    with pytest.raises(TagNotFoundError):
        DocumentRepository(db_session).unlink_tag(TagLinkCommand(description_id="tag-5", tag_id=tag.tag_id))


def test_curating_an_unknown_document_returns_none(db_session) -> None:
    """The service turns this into the 404; the repository does not raise on a missing parent row."""
    assert DocumentRepository(db_session).link_tag(TagLinkCommand(description_id="nada", tag_id=1)) is None


def test_linking_and_unlinking_an_entity(db_session, generate_archive_doc) -> None:
    entity = _entity(db_session, name="Curitiba")
    generate_archive_doc(description_id="ent-1", original_title="Documento")
    repository = DocumentRepository(db_session)

    linked = repository.link_entity(EntityLinkCommand(description_id="ent-1", entity_id=entity.entity_id))
    assert linked is not None
    assert [item.name for item in linked.entities] == ["Curitiba"]
    assert linked.review_status == ArchiveReviewStatus.HUMAN_APPROVED

    unlinked = repository.unlink_entity(EntityLinkCommand(description_id="ent-1", entity_id=entity.entity_id))
    assert unlinked is not None
    assert unlinked.entities == []
    assert repository.list_revisions("ent-1")[0].changes == {"entities": {"old": ["Curitiba"], "new": []}}


def test_linking_an_entity_that_does_not_exist_is_a_business_error(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="ent-2", original_title="Documento")

    with pytest.raises(EntityNotFoundError):
        DocumentRepository(db_session).link_entity(EntityLinkCommand(description_id="ent-2", entity_id=424242))


def test_the_human_tag_edit_survives_a_transfer(db_session, generate_archive_doc, generate_archive_dto) -> None:
    """
    Governance: a document the archivist touched is no longer writable by the pipeline.

    Without this, the next incremental load would silently undo the curation — the exact failure
    ``ai_writable_documents`` exists to prevent.
    """
    tag = _tag(db_session, name="curado")
    generate_archive_doc(description_id="tag-6", original_title="Documento", staging_content_hash="hash_old")
    DocumentRepository(db_session).link_tag(TagLinkCommand(description_id="tag-6", tag_id=tag.tag_id))

    overwritten = DocumentRepository(db_session).upsert_archive_document(
        generate_archive_dto(description_id="tag-6", original_title="Sobrescrito", staging_content_hash="hash_new")
    )

    assert overwritten is False
    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, "tag-6")
    assert stored is not None
    assert stored.original_title == "Documento"


# ==========================================
# DIFFUSION (Fase 4)
# ==========================================


def test_documents_are_not_published_by_default(db_session, generate_archive_doc) -> None:
    """Adding the column to a collection with thousands of rows must not publish anything."""
    generate_archive_doc(description_id="pub-def", original_title="Documento")
    db_session.flush()

    stored = db_session.get(ArchiveDocument, "pub-def")
    assert stored is not None
    assert stored.is_published is False


def test_the_diffusion_gate_filters_the_search(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="pub-yes", original_title="Publicado", is_published=True)
    generate_archive_doc(description_id="pub-no", original_title="Interno", is_published=False)
    db_session.flush()

    docs, total, _facets = DocumentRepository(db_session).search(DocumentSearchQuery(published_only=True))

    assert total == 1
    assert [doc.description_id for doc in docs] == ["pub-yes"]


def test_publication_does_not_lock_the_record_against_the_ai(
    db_session, generate_archive_doc, generate_archive_dto
) -> None:
    """
    The reason ``is_published`` exists instead of reusing ``HUMAN_APPROVED``.

    A *published* record must still be improvable by the pipeline; a *reviewed* one must not. If
    these were the same column, publishing a description would freeze it forever.
    """
    generate_archive_doc(
        description_id="pub-ai",
        original_title="Antes",
        staging_content_hash="hash_a",
        is_published=True,
        review_status=ArchiveReviewStatus.AI_APPROVED,
    )

    updated = DocumentRepository(db_session).upsert_archive_document(
        generate_archive_dto(description_id="pub-ai", original_title="Depois", staging_content_hash="hash_b")
    )

    assert updated is True
    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, "pub-ai")
    assert stored is not None
    assert stored.original_title == "Depois"
    assert stored.is_published is True


def test_the_archivist_can_publish_through_the_review_command(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="pub-cmd", original_title="Documento")
    repository = DocumentRepository(db_session)

    summary = repository.update_review(DocumentReviewCommand(description_id="pub-cmd", is_published=True))

    assert summary is not None
    assert summary.is_published is True
    assert repository.list_revisions("pub-cmd")[0].changes == {"is_published": {"old": False, "new": True}}


def test_access_conditions_is_editable_as_an_isad_g_field(db_session, generate_archive_doc) -> None:
    """ISAD(G) 4.1 stopped being dropped at the transfer, so the archivist can now state it."""
    generate_archive_doc(description_id="acc-1", original_title="Documento")

    summary = DocumentRepository(db_session).update_review(
        DocumentReviewCommand(description_id="acc-1", access_conditions="Consulta mediante autorização")
    )

    assert summary is not None
    assert summary.access_conditions == "Consulta mediante autorização"

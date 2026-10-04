"""Integration tests of the human curation surface (real PostgreSQL)."""

from datetime import date

from sqlalchemy import select

from memoria_curitibana.domains.archive.models import ArchiveDocument, ArchiveDocumentRevision
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    apply_excerpts_in_python,
    effective_column_sql,
)
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.text_quality_schema import TemplateCreateCommand, TemplateUpdateCommand


def _title_template(db_session, text: str = "Registros Fotográficos -") -> None:
    TextQualityRepository(db_session).create_template(TemplateCreateCommand(text=text, scope=["TITLE"]))
    db_session.flush()


# ==========================================
# AUDIT TRAIL
# ==========================================


def test_update_review_can_fix_any_isad_g_field(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="edit-1", original_title="Título antigo")

    summary = DocumentRepository(db_session).update_review(
        DocumentReviewCommand(
            description_id="edit-1",
            document_date=date(1954, 3, 15),
            reference_code="BR PR IPPUC",
            level="Item",
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

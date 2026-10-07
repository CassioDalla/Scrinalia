"""Integration tests of the deletion of a description and of the ledger it leaves (real PostgreSQL).

Two facts are pinned here, and both are the reason the feature is defensible rather than convenient:

* a node with children **cannot** be deleted — the self-referencing FK is ``RESTRICT`` because every
  descendant's materialised ``path`` carries its ancestors' ids, so removing a branch would leave a
  subtree pointing at a prefix that no longer exists;
* the ledger outlives the document. The revision table cascades with it, so a revision written for a
  deleted document would be destroyed by the delete it was recording; the snapshot here is the only
  record of what was removed.
"""

from datetime import date

import pytest
from sqlalchemy import func, select

from scrinalia.domains.archive.exceptions import DocumentHasChildrenError, DocumentNotFoundError
from scrinalia.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentDeletion,
    ArchiveDocumentRevision,
    ArchiveDocumentTag,
    ArchiveReviewStatus,
    ArchiveTag,
)
from scrinalia.domains.archive.repository.document_repo import DocumentRepository
from scrinalia.domains.archive.schemas.command_schema import DocumentReviewCommand, TagLinkCommand
from scrinalia.domains.archive.services.document_service import DocumentService


def _tag(db_session, name: str = "urbanismo") -> ArchiveTag:
    tag = ArchiveTag(name=name)
    db_session.add(tag)
    db_session.flush()
    return tag


# ==========================================
# THE GUARD
# ==========================================


def test_a_node_with_children_is_refused(db_session, generate_archive_doc) -> None:
    """The refusal names how many children are in the way, and nothing is written."""
    generate_archive_doc(description_id="parent-1", original_title="Fundo")
    generate_archive_doc(description_id="child-1", original_title="Série", parent_id="parent-1")
    generate_archive_doc(description_id="child-2", original_title="Outra série", parent_id="parent-1")

    service = DocumentService(DocumentRepository(db_session))
    with pytest.raises(DocumentHasChildrenError) as error:
        service.delete("parent-1")

    assert "2 descrição" in str(error.value)
    assert db_session.get(ArchiveDocument, "parent-1") is not None
    assert db_session.scalar(select(func.count()).select_from(ArchiveDocumentDeletion)) == 0


def test_a_leaf_is_deleted(db_session, generate_archive_doc) -> None:
    """A leaf goes, and the ledger row is what is left of it."""
    generate_archive_doc(
        description_id="leaf-1",
        original_title="Registros Fotográficos - Praça",
        final_title="Praça Castro Alves",
        reference_code="BR PRADAP IPPUC FOTOGRAFIA 00575",
        document_date=date(1940, 1, 1),
    )

    service = DocumentService(DocumentRepository(db_session))
    entry = service.delete("leaf-1", changed_by="cassio", note="duplicata da 00574")

    assert db_session.get(ArchiveDocument, "leaf-1") is None
    assert entry.description_id == "leaf-1"
    assert entry.title == "Praça Castro Alves"
    assert entry.reference_code == "BR PRADAP IPPUC FOTOGRAFIA 00575"
    assert entry.deleted_by == "cassio"
    assert entry.note == "duplicata da 00574"
    assert entry.children_count == 0


def test_a_missing_document_is_a_not_found(db_session) -> None:
    """The route answers 404 for an id the collection does not have."""
    service = DocumentService(DocumentRepository(db_session))
    with pytest.raises(DocumentNotFoundError):
        service.delete("nao-existe")


# ==========================================
# THE SNAPSHOT
# ==========================================


def test_the_snapshot_keeps_the_isad_content(db_session, generate_archive_doc) -> None:
    """Every ISAD(G) column is copied, because after the write there is nothing to reference."""
    generate_archive_doc(
        description_id="leaf-2",
        original_title="Título original",
        scope_content="Acervo de 35.327 fotografias",
        producers="IPPUC",
        language_name="pt-BR",
        access_conditions="Consulta mediante autorização",
        document_date=date(1994, 1, 1),
    )

    entry = DocumentService(DocumentRepository(db_session)).delete("leaf-2")

    assert entry.snapshot["original_title"] == "Título original"
    assert entry.snapshot["scope_content"] == "Acervo de 35.327 fotografias"
    assert entry.snapshot["producers"] == "IPPUC"
    assert entry.snapshot["language_name"] == "pt-BR"
    assert entry.snapshot["access_conditions"] == "Consulta mediante autorização"
    # Dates travel as ISO strings: JSONB cannot hold a ``date``, and the ledger has to be readable.
    assert entry.snapshot["document_date"] == "1994-01-01"
    # The generated full-text column and the vector are derived indexes, not content: neither can be
    # written back, so neither belongs in a snapshot meant to be read and rebuilt by hand.
    assert "search_vector" not in entry.snapshot
    assert "embedding" not in entry.snapshot


def test_the_snapshot_survives_what_cascades(db_session, generate_archive_doc) -> None:
    """The links and the revisions die with the document; the ledger does not."""
    generate_archive_doc(description_id="leaf-3", original_title="Item")
    tag = _tag(db_session)
    repository = DocumentRepository(db_session)
    repository.link_tag(TagLinkCommand(description_id="leaf-3", tag_id=tag.tag_id), changed_by="ana")
    repository.update_review(
        DocumentReviewCommand(description_id="leaf-3", archivist_notes="conferido", changed_by="ana")
    )
    assert db_session.scalar(select(func.count()).select_from(ArchiveDocumentTag)) == 1
    # Two revisions: the tag link is itself a curated write, and so is the field edit.
    assert db_session.scalar(select(func.count()).select_from(ArchiveDocumentRevision)) == 2

    entry = DocumentService(repository).delete("leaf-3", changed_by="ana")

    assert db_session.scalar(select(func.count()).select_from(ArchiveDocumentTag)) == 0
    assert db_session.scalar(select(func.count()).select_from(ArchiveDocumentRevision)) == 0
    # The tag itself is untouched: deleting a description is not a statement about the vocabulary.
    assert db_session.get(ArchiveTag, tag.tag_id) is not None
    assert db_session.get(ArchiveDocumentDeletion, entry.deletion_id) is not None


# ==========================================
# READING THE LEDGER
# ==========================================


def test_the_ledger_lists_newest_first_and_filters_by_a_term(db_session, generate_archive_doc) -> None:
    """The screen needs both: the last deletions, and the one a colleague mentions by name."""
    generate_archive_doc(description_id="gone-1", original_title="Praça Castro Alves", reference_code="BR A 1")
    generate_archive_doc(description_id="gone-2", original_title="Jardim Botânico", reference_code="BR B 2")
    service = DocumentService(DocumentRepository(db_session))
    service.delete("gone-1")
    service.delete("gone-2")

    page = service.list_deletions(limit=10, offset=0)
    assert page.total == 2
    assert [item.description_id for item in page.items] == ["gone-2", "gone-1"]

    filtered = service.list_deletions(term="castro")
    assert filtered.total == 1
    assert filtered.items[0].description_id == "gone-1"

    by_code = service.list_deletions(term="BR B")
    assert by_code.total == 1
    assert by_code.items[0].description_id == "gone-2"

    by_id = service.list_deletions(term="gone-1")
    assert by_id.total == 1


def test_a_wildcard_in_the_search_box_is_a_character(db_session, generate_archive_doc) -> None:
    """``%`` must not mean "everything": the ledger would answer the whole trail to a typo."""
    generate_archive_doc(description_id="gone-3", original_title="Sem por cento")
    generate_archive_doc(description_id="gone-4", original_title="Com 100% de área")
    service = DocumentService(DocumentRepository(db_session))
    service.delete("gone-3")
    service.delete("gone-4")

    assert service.list_deletions(term="%").total == 1


def test_the_page_is_a_page(db_session, generate_archive_doc) -> None:
    """``total`` counts the whole trail, not the page — the screen's footer depends on it."""
    for index in range(3):
        generate_archive_doc(description_id=f"gone-p{index}", original_title=f"Item {index}")
    service = DocumentService(DocumentRepository(db_session))
    for index in range(3):
        service.delete(f"gone-p{index}")

    page = service.list_deletions(limit=2, offset=0)
    assert (page.total, page.limit, page.offset, len(page.items)) == (3, 2, 0, 2)


def test_deleting_a_description_is_not_a_review_status(db_session, generate_archive_doc) -> None:
    """The write removes the row; it does not mark it. A "deleted" status would be a soft delete."""
    doc = generate_archive_doc(description_id="leaf-4", original_title="Item")
    doc.review_status = ArchiveReviewStatus.HUMAN_APPROVED
    db_session.flush()

    DocumentService(DocumentRepository(db_session)).delete("leaf-4")

    assert db_session.get(ArchiveDocument, "leaf-4") is None

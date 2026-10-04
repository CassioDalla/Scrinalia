from datetime import date

import pytest
from sqlalchemy import select

from memoria_curitibana.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveMacroCategory,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTypology,
)
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery

# ==========================================
# UPSERT AND DATA PIPELINE (ETL) TESTS
# ==========================================


def test_upsert_archive_document_insert_new(use_test_db, db_session, generate_archive_dto):
    """Scenario 1: Insertion of a brand-new document coming from Staging."""
    repo = DocumentRepository(db_session)
    new_dto = generate_archive_dto(description_id="1", original_title="Inédito", staging_content_hash="hash_1")

    inserted = repo.upsert_archive_document(new_dto)
    db_session.commit()

    assert inserted is True
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="1")).scalar_one()
    assert doc_db.original_title == "Inédito"


def test_upsert_archive_document_ignore_same_hash(use_test_db, db_session, generate_archive_dto):
    """Scenario 2: Incremental Load. A document with the same Hash must be ignored."""
    repo = DocumentRepository(db_session)
    original_dto = generate_archive_dto(description_id="2", original_title="Original", staging_content_hash="hash_2")
    repo.upsert_archive_document(original_dto)
    db_session.commit()

    repeated_dto = generate_archive_dto(description_id="2", original_title="Falso", staging_content_hash="hash_2")
    repeated_inserted = repo.upsert_archive_document(repeated_dto)
    db_session.commit()

    assert repeated_inserted is False
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="2")).scalar_one()
    assert doc_db.original_title == "Original"


def test_upsert_archive_document_update_resets_ai(use_test_db, db_session, generate_archive_dto):
    """
    Scenario 3: CDC. If the Hash changed in Staging, it updates the data AND erases AI
    traces that ARE present in the new payload (execution_log={} and PENDING_AI here),
    while preserving metadata that this transfer does not carry.
    """
    repo = DocumentRepository(db_session)
    original_dto = generate_archive_dto(
        description_id="3",
        original_title="Antigo",
        staging_content_hash="hash_3",
        execution_log={"ner_spacy_v1": "DONE"},
        review_status=ArchiveReviewStatus.NEEDS_REVIEW,
        reference_code="BR PR CUR 001",
    )
    repo.upsert_archive_document(original_dto)
    db_session.commit()

    new_dto = generate_archive_dto(
        description_id="3",
        original_title="Novo Título",
        staging_content_hash="hash_3_NOVO",
        execution_log={},
        review_status=ArchiveReviewStatus.PENDING_AI,
    )
    new_inserted = repo.upsert_archive_document(new_dto)
    db_session.commit()

    assert new_inserted is True
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="3")).scalar_one()
    assert doc_db.original_title == "Novo Título"
    assert doc_db.execution_log == {}  # The log present in the payload was reset!
    assert doc_db.review_status == ArchiveReviewStatus.PENDING_AI
    # A field NOT sent by this transfer payload must survive the update.
    assert doc_db.reference_code == "BR PR CUR 001"


def test_upsert_archive_document_preserves_created_at(use_test_db, db_session, generate_archive_dto):
    """Regression: reprocessing a document must not reset its created_at."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="created", original_title="Antigo", staging_content_hash="h1")
    )
    db_session.commit()

    created_at_before = db_session.get(ArchiveDocument, "created").created_at

    repo.upsert_archive_document(
        generate_archive_dto(description_id="created", original_title="Novo", staging_content_hash="h2")
    )
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(ArchiveDocument, "created")
    assert stored.original_title == "Novo"
    assert stored.created_at == created_at_before


def test_upsert_archive_document_blocked_by_human_approved(use_test_db, db_session, generate_archive_dto):
    """Scenario 4: Governance. A document with HUMAN_APPROVED status blocks the ETL overwrite."""
    repo = DocumentRepository(db_session)
    original_dto = generate_archive_dto(
        description_id="4",
        original_title="Revisado Perfeito",
        staging_content_hash="hash_4",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )
    repo.upsert_archive_document(original_dto)
    db_session.commit()

    attack_dto = generate_archive_dto(
        description_id="4", original_title="Lixo da Staging", staging_content_hash="hash_4_NOVO"
    )
    attack_inserted = repo.upsert_archive_document(attack_dto)
    db_session.commit()

    assert attack_inserted is False
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="4")).scalar_one()
    assert doc_db.original_title == "Revisado Perfeito"


# ==========================================
# READING AND CURATION TESTS
# ==========================================


def test_search_filters_by_term_and_paginates(use_test_db, db_session, generate_archive_dto):
    """Text search returns only the matches and the correct total, respecting the page."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="s1", original_title="Matadouro Municipal", staging_content_hash="h1")
    )
    repo.upsert_archive_document(
        generate_archive_dto(description_id="s2", original_title="Praça do Gaúcho", staging_content_hash="h2")
    )
    db_session.commit()

    docs, total = repo.search(DocumentSearchQuery(term="Matadouro"))
    assert total == 1
    assert docs[0].description_id == "s1"

    page, total_overall = repo.search(DocumentSearchQuery(limit=1, offset=0))
    assert total_overall == 2
    assert len(page) == 1


def test_update_review_blinds_document_as_human_approved(use_test_db, db_session, generate_archive_dto):
    """Human editing applies the fields and marks the document as HUMAN_APPROVED."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="r1", original_title="Original", staging_content_hash="hr1")
    )
    db_session.commit()

    updated = repo.update_review(
        DocumentReviewCommand(description_id="r1", final_title="Título Revisado", archivist_notes="ok")
    )
    db_session.commit()

    assert updated is not None
    assert updated.review_status == ArchiveReviewStatus.HUMAN_APPROVED
    assert updated.final_title == "Título Revisado"


def test_update_review_returns_none_for_missing_document(use_test_db, db_session):
    repo = DocumentRepository(db_session)
    assert repo.update_review(DocumentReviewCommand(description_id="nao-existe", final_title="x")) is None


# ==========================================
# MACRO CATEGORY VOTE (SUBJECT AXIS)
# ==========================================


def _link_tag(db_session, description_id: str, tag_id: int) -> None:
    db_session.add(ArchiveDocumentTag(description_id=description_id, tag_id=tag_id))


def test_search_votes_macro_categories_by_tag_count(use_test_db, db_session, generate_archive_doc):
    """The read view exposes the winning category first, counting only categorized tags."""
    repo = DocumentRepository(db_session)
    urban = ArchiveMacroCategory(name="Urbanismo")
    health = ArchiveMacroCategory(name="Saúde")
    db_session.add_all([urban, health])
    db_session.flush()

    doc = generate_archive_doc(description_id="vote_1", original_title="Plano Urbano de Curitiba")

    tags = [
        ArchiveTag(name="pavimentação", macro_category_id=urban.category_id),
        ArchiveTag(name="calçamento", macro_category_id=urban.category_id),
        ArchiveTag(name="dengue", macro_category_id=health.category_id),
        ArchiveTag(name="sem categoria", macro_category_id=None),
    ]
    db_session.add_all(tags)
    db_session.commit()

    for tag in tags:
        _link_tag(db_session, doc.description_id, tag.tag_id)
    db_session.commit()

    docs, total = repo.search(DocumentSearchQuery(term="Plano Urbano"))

    assert total == 1
    assert [(vote.name, vote.tag_count) for vote in docs[0].macro_categories] == [("Urbanismo", 2), ("Saúde", 1)]

    detail = repo.get_by_id(doc.description_id)
    assert detail is not None
    assert [(vote.category_id, vote.tag_count) for vote in detail.macro_categories] == [
        (urban.category_id, 2),
        (health.category_id, 1),
    ]


def test_tag_edit_reflects_on_documents_without_touching_the_documents_table(
    use_test_db, db_session, generate_archive_doc
):
    """
    Editing a tag's macro category must be visible on every linked document immediately,
    and must not write to ``archive_documents`` (the vote is derived on read).
    """
    repo = DocumentRepository(db_session)
    urban = ArchiveMacroCategory(name="Urbanismo")
    health = ArchiveMacroCategory(name="Saúde")
    db_session.add_all([urban, health])
    db_session.flush()

    doc = generate_archive_doc(description_id="reflect_1", original_title="Documento Refletido")
    tag = ArchiveTag(name="habitação", macro_category_id=urban.category_id)
    db_session.add(tag)
    db_session.commit()

    _link_tag(db_session, doc.description_id, tag.tag_id)
    db_session.commit()

    before = db_session.get(ArchiveDocument, doc.description_id)
    assert before is not None
    updated_at_before = before.updated_at

    tag.macro_category_id = health.category_id
    db_session.commit()
    db_session.expire_all()

    after = db_session.get(ArchiveDocument, doc.description_id)
    assert after is not None
    assert after.updated_at == updated_at_before

    docs, _ = repo.search(DocumentSearchQuery(term="Documento Refletido"))
    assert [vote.name for vote in docs[0].macro_categories] == ["Saúde"]


# ==========================================
# FULL-TEXT SEARCH (TERM)
# ==========================================


def test_search_stems_portuguese_and_ignores_accents(use_test_db, db_session, generate_archive_dto):
    """The portuguese dictionary stems (enchente ~ enchentes) and unaccent folds accents."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(
            description_id="fts1",
            original_title="Enchentes no Batel",
            scope_content="A praça do Gaúcho alagou",
            staging_content_hash="h1",
        )
    )
    repo.upsert_archive_document(
        generate_archive_dto(
            description_id="fts2",
            original_title="Relatório de obras",
            scope_content="Pavimentação concluída",
            staging_content_hash="h2",
        )
    )
    db_session.commit()

    # A singular query finds the stored plural.
    docs, total = repo.search(DocumentSearchQuery(term="enchente"))
    assert (total, [doc.description_id for doc in docs]) == (1, ["fts1"])

    # A query without the accent finds the accented word.
    docs, _ = repo.search(DocumentSearchQuery(term="gaucho"))
    assert [doc.description_id for doc in docs] == ["fts1"]

    # A prefix of a word still being typed.
    docs, _ = repo.search(DocumentSearchQuery(term="relat"))
    assert [doc.description_id for doc in docs] == ["fts2"]


def test_search_ranks_title_hits_above_body_hits(use_test_db, db_session, generate_archive_dto):
    """Title weight A beats body weight B, and the relevance is exposed on the read view."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(
            description_id="rank_title",
            original_title="Matadouro Municipal",
            scope_content="Sem relação com o termo",
            staging_content_hash="h1",
        )
    )
    repo.upsert_archive_document(
        generate_archive_dto(
            description_id="rank_body",
            original_title="Relatório anual",
            scope_content="Reforma do matadouro municipal",
            staging_content_hash="h2",
        )
    )
    db_session.commit()

    docs, total = repo.search(DocumentSearchQuery(term="matadouro"))

    assert total == 2
    assert [doc.description_id for doc in docs] == ["rank_title", "rank_body"]
    assert docs[0].rank is not None and docs[1].rank is not None
    assert docs[0].rank > docs[1].rank > 0


def test_search_without_a_term_does_not_expose_a_rank(use_test_db, db_session, generate_archive_doc):
    """Browsing the collection is not a search: there is no relevance to show."""
    repo = DocumentRepository(db_session)
    generate_archive_doc(description_id="browse1", original_title="Qualquer um")

    docs, total = repo.search(DocumentSearchQuery())

    assert total == 1
    assert docs[0].rank is None


def test_search_returns_empty_for_a_term_that_matches_nothing(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    generate_archive_doc(description_id="none1", original_title="Documento qualquer")

    docs, total = repo.search(DocumentSearchQuery(term="zznada"))

    assert (total, docs) == (0, [])


def test_search_falls_back_to_substring_for_a_mid_word_term(use_test_db, db_session, generate_archive_dto):
    """FTS cannot see inside a word, so the old contains behaviour is kept as a fallback."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="fb1", original_title="Urbanismo em Curitiba", staging_content_hash="h1")
    )
    db_session.commit()

    docs, total = repo.search(DocumentSearchQuery(term="rbanis"))

    assert (total, [doc.description_id for doc in docs]) == (1, ["fb1"])


# ==========================================
# SEARCH ACROSS TAGS AND ENTITIES
# ==========================================


def test_search_finds_a_document_through_its_tag_and_entity(use_test_db, db_session, generate_archive_doc):
    """A document whose own text lacks the term must still surface through the taxonomy."""
    repo = DocumentRepository(db_session)
    doc = generate_archive_doc(
        description_id="tax1", original_title="Documento sem pistas", scope_content="texto neutro"
    )
    tag = ArchiveTag(name="pavimentação asfáltica")
    entity = ArchiveEntity(name="Batel", entity_type="LOC")
    db_session.add_all([tag, entity])
    db_session.commit()
    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=tag.tag_id),
            ArchiveDocumentEntity(description_id=doc.description_id, entity_id=entity.entity_id),
        ]
    )
    db_session.commit()

    by_tag, total_tag = repo.search(DocumentSearchQuery(term="pavimentação"))
    assert (total_tag, [item.description_id for item in by_tag]) == (1, ["tax1"])
    assert by_tag[0].rank is not None and by_tag[0].rank > 0

    by_entity, total_entity = repo.search(DocumentSearchQuery(term="batel"))
    assert (total_entity, [item.description_id for item in by_entity]) == (1, ["tax1"])


def test_search_does_not_duplicate_a_document_with_several_matching_tags(use_test_db, db_session, generate_archive_doc):
    """``EXISTS`` instead of a join: the page and the total must not double-count."""
    repo = DocumentRepository(db_session)
    doc = generate_archive_doc(description_id="dup1", original_title="Sem o termo no texto")
    tags = [ArchiveTag(name="saneamento básico"), ArchiveTag(name="saneamento urbano")]
    db_session.add_all(tags)
    db_session.commit()
    for tag in tags:
        _link_tag(db_session, doc.description_id, tag.tag_id)
    db_session.commit()

    docs, total = repo.search(DocumentSearchQuery(term="saneamento"))

    assert total == 1
    assert [item.description_id for item in docs] == ["dup1"]


# ==========================================
# FACETED FILTERS
# ==========================================


def test_search_filters_by_typology(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    dossier = ArchiveTypology(name="Dossiê")
    photo = ArchiveTypology(name="Fotografia")
    db_session.add_all([dossier, photo])
    db_session.commit()
    generate_archive_doc(description_id="t1", original_title="Doc dossiê", typology_id=dossier.typology_id)
    generate_archive_doc(description_id="t2", original_title="Doc foto", typology_id=photo.typology_id)

    docs, total = repo.search(DocumentSearchQuery(typology_id=photo.typology_id))

    assert (total, [item.description_id for item in docs]) == (1, ["t2"])


def test_search_filters_by_macro_category(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    urban = ArchiveMacroCategory(name="Urbanismo")
    db_session.add(urban)
    db_session.flush()
    tag = ArchiveTag(name="pavimentação", macro_category_id=urban.category_id)
    db_session.add(tag)
    db_session.commit()

    with_category = generate_archive_doc(description_id="mc1", original_title="Com gaveta")
    generate_archive_doc(description_id="mc2", original_title="Sem gaveta")
    _link_tag(db_session, with_category.description_id, tag.tag_id)
    db_session.commit()

    docs, total = repo.search(DocumentSearchQuery(macro_category_id=urban.category_id))

    assert (total, [item.description_id for item in docs]) == (1, ["mc1"])


def test_search_filters_by_entity_type(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    place = ArchiveEntity(name="Batel", entity_type="LOC")
    institution = ArchiveEntity(name="Prefeitura de Curitiba", entity_type="ORG")
    db_session.add_all([place, institution])
    db_session.commit()

    doc_place = generate_archive_doc(description_id="e1", original_title="Lugar")
    doc_org = generate_archive_doc(description_id="e2", original_title="Instituição")
    db_session.add_all(
        [
            ArchiveDocumentEntity(description_id=doc_place.description_id, entity_id=place.entity_id),
            ArchiveDocumentEntity(description_id=doc_org.description_id, entity_id=institution.entity_id),
        ]
    )
    db_session.commit()

    docs, total = repo.search(DocumentSearchQuery(entity_type="ORG"))

    assert (total, [item.description_id for item in docs]) == (1, ["e2"])


def test_search_filters_by_date_range(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    generate_archive_doc(description_id="d1954", original_title="Antigo", document_date=date(1954, 3, 15))
    generate_archive_doc(description_id="d1980", original_title="Recente", document_date=date(1980, 5, 10))
    generate_archive_doc(description_id="dNone", original_title="Sem data")

    docs, total = repo.search(DocumentSearchQuery(date_from=date(1950, 1, 1), date_to=date(1960, 12, 31)))
    assert (total, [item.description_id for item in docs]) == (1, ["d1954"])

    docs, total = repo.search(DocumentSearchQuery(date_from=date(1960, 1, 1)))
    assert (total, [item.description_id for item in docs]) == (1, ["d1980"])


def test_search_combines_term_and_facet_with_stable_pagination(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    urban = ArchiveMacroCategory(name="Urbanismo")
    health = ArchiveMacroCategory(name="Saúde")
    db_session.add_all([urban, health])
    db_session.flush()
    urban_tag = ArchiveTag(name="pavimentação urbana", macro_category_id=urban.category_id)
    health_tag = ArchiveTag(name="pavimentação sanitária", macro_category_id=health.category_id)
    db_session.add_all([urban_tag, health_tag])
    db_session.commit()

    for description_id in ("c1", "c2"):
        doc = generate_archive_doc(description_id=description_id, original_title=f"Pavimentação {description_id}")
        _link_tag(db_session, doc.description_id, urban_tag.tag_id)
    other = generate_archive_doc(description_id="c3", original_title="Pavimentação sanitária")
    _link_tag(db_session, other.description_id, health_tag.tag_id)
    db_session.commit()

    first_page, total = repo.search(
        DocumentSearchQuery(term="pavimentação", macro_category_id=urban.category_id, limit=1, offset=0)
    )
    second_page, _ = repo.search(
        DocumentSearchQuery(term="pavimentação", macro_category_id=urban.category_id, limit=1, offset=1)
    )

    assert total == 2
    assert len(first_page) == 1 and len(second_page) == 1
    assert {first_page[0].description_id, second_page[0].description_id} == {"c1", "c2"}


# ==========================================
# SEMANTIC SEARCH (EMBEDDINGS)
# ==========================================


def _vector(*components: float) -> list[float]:
    """Builds a 384-dim vector with the given leading components (rest zero)."""
    base = [0.0] * 384
    for index, value in enumerate(components):
        base[index] = value
    return base


def test_semantic_search_orders_by_cosine_similarity_and_skips_documents_without_embedding(
    use_test_db, db_session, generate_archive_doc
):
    repo = DocumentRepository(db_session)
    generate_archive_doc(description_id="sem1", original_title="Enchentes", embedding=_vector(1.0))
    generate_archive_doc(description_id="sem2", original_title="Obras", embedding=_vector(0.0, 1.0))
    generate_archive_doc(description_id="sem3", original_title="Sem vetor")

    docs, total = repo.search(DocumentSearchQuery(term="alagamento", mode="semantic"), query_embedding=_vector(1.0))

    # Only embedded documents are candidates; the closest one comes first.
    assert total == 2
    assert [doc.description_id for doc in docs] == ["sem1", "sem2"]
    assert docs[0].rank == pytest.approx(1.0, abs=1e-5)
    assert docs[1].rank == pytest.approx(0.0, abs=1e-5)


def test_semantic_search_respects_facets(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    dossier = ArchiveTypology(name="Dossiê")
    photo = ArchiveTypology(name="Fotografia")
    db_session.add_all([dossier, photo])
    db_session.commit()

    generate_archive_doc(
        description_id="fac1", original_title="A", embedding=_vector(1.0), typology_id=dossier.typology_id
    )
    generate_archive_doc(
        description_id="fac2", original_title="B", embedding=_vector(1.0), typology_id=photo.typology_id
    )

    docs, total = repo.search(
        DocumentSearchQuery(term="x", mode="semantic", typology_id=photo.typology_id),
        query_embedding=_vector(1.0),
    )

    assert (total, [doc.description_id for doc in docs]) == (1, ["fac2"])


def test_semantic_mode_without_a_query_embedding_falls_back_to_browsing(use_test_db, db_session, generate_archive_doc):
    """A semantic request with no term carries no vector, so it must not crash."""
    repo = DocumentRepository(db_session)
    generate_archive_doc(description_id="noemb", original_title="Qualquer", embedding=_vector(1.0))

    docs, total = repo.search(DocumentSearchQuery(mode="semantic"))

    assert total == 1
    assert docs[0].rank is None


def test_lexical_mode_ignores_the_query_embedding(use_test_db, db_session, generate_archive_doc):
    repo = DocumentRepository(db_session)
    generate_archive_doc(description_id="lex1", original_title="Matadouro Municipal", embedding=_vector(1.0))

    docs, total = repo.search(DocumentSearchQuery(term="matadouro"), query_embedding=_vector(1.0))

    assert total == 1
    assert docs[0].rank is not None and docs[0].rank > 0

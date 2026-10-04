"""Integration tests of the text-quality repository (real PostgreSQL)."""

from datetime import date

import pytest
from sqlalchemy import select

from memoria_curitibana.domains.archive.domain.text_quality import SuggestionCandidate, normalize_excerpt
from memoria_curitibana.domains.archive.models import ArchiveDocument, DomainTextTemplate
from memoria_curitibana.domains.archive.repository.text_quality_repo import (
    ExcerptRule,
    TextQualityRepository,
    effective_column_sql,
    effective_title_sql,
    embedding_hash_sql,
    embedding_text_sql,
    normalized_column_sql,
)
from memoria_curitibana.domains.archive.schemas.text_quality_schema import (
    TemplateCreateCommand,
    TemplateUpdateCommand,
)

BLOCK = "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do Planejamento"


@pytest.fixture
def repo(db_session) -> TextQualityRepository:
    return TextQualityRepository(db_session)


def _add_template(db_session, **overrides) -> DomainTextTemplate:
    data = {
        "text": "Registros Fotográficos -",
        "fingerprint": (overrides.get("text") or "x") * 1,
        "action": "IGNORE",
        "replacement": "",
        "scope": ["EMBEDDING", "NER"],
        "source": "HUMAN",
        "status": "APPROVED",
        "is_active": True,
    }
    data.update(overrides)
    data["fingerprint"] = f"{data['text']}-{data['status']}-{data['is_active']}-{data['scope']}"[:64]
    row = DomainTextTemplate(**data)
    db_session.add(row)
    db_session.flush()
    return row


# ==========================================
# NORMALIZATION PARITY (the measured divergence)
# ==========================================


def test_sql_normalization_matches_the_python_normalization(db_session, generate_archive_doc) -> None:
    """
    Regression for the divergence that a suggestion would silently fail on: PostgreSQL's
    ``[[:space:]]`` does not match U+00A0 while Python's ``\\s`` does, and the collapse
    used to leave leading/trailing spaces behind.
    """
    raw = "  dois\t\tespaços\u00a0irregulares \n e   quebras  "
    doc = generate_archive_doc(original_title=raw)

    sql_value = db_session.scalar(
        select(normalized_column_sql("original_title")).where(ArchiveDocument.description_id == doc.description_id)
    )
    assert sql_value == normalize_excerpt(raw)


def test_effective_column_removes_only_the_approved_excerpt(db_session, generate_archive_doc) -> None:
    doc = generate_archive_doc(original_title="Registros Fotográficos - Rua Izaac Ferreira da Cruz")
    _add_template(db_session, text="Registros Fotográficos -")
    _add_template(db_session, text="Pesquisa", status="SUGGESTED", is_active=False)
    _add_template(db_session, text="Fotográficos", status="REJECTED", is_active=True)
    _add_template(db_session, text="Registros Fotográficos", status="APPROVED", is_active=False)
    db_session.flush()

    rules = TextQualityRepository(db_session).get_active_rules()
    value = db_session.scalar(
        select(effective_column_sql("original_title", rules)).where(
            ArchiveDocument.description_id == doc.description_id
        )
    )

    assert value == "Rua Izaac Ferreira da Cruz"


def test_effective_text_prefers_the_human_final_title(db_session, generate_archive_doc) -> None:
    doc = generate_archive_doc(original_title="Registros Fotográficos - Rua A", final_title="Rua B")
    _add_template(db_session, text="Registros Fotográficos -")
    db_session.flush()

    rules = TextQualityRepository(db_session).get_active_rules()
    value = db_session.scalar(
        select(effective_title_sql(rules)).where(ArchiveDocument.description_id == doc.description_id)
    )

    assert value == "Rua B"


def test_effective_text_grows_when_an_excerpt_is_approved(db_session, generate_archive_doc) -> None:
    """The catalogue is read on every composition, so approving it changes the text at once."""
    doc = generate_archive_doc(original_title="Rua X", scope_content=BLOCK)

    def text_for(rules):
        return db_session.scalar(
            select(embedding_text_sql(rules)).where(ArchiveDocument.description_id == doc.description_id)
        )

    before = text_for([])
    assert before == f"Rua X\n{BLOCK}"

    _add_template(db_session, text=BLOCK)
    db_session.flush()
    after = text_for(TextQualityRepository(db_session).get_active_rules())

    assert after == "Rua X"


def test_embedding_hash_changes_when_the_effective_text_changes(db_session, generate_archive_doc) -> None:
    """The stamp is the MD5 of the effective text, so a catalog decision re-queues the document."""
    doc = generate_archive_doc(original_title="Rua X", scope_content=BLOCK)
    condition = ArchiveDocument.description_id == doc.description_id

    before = db_session.scalar(select(embedding_hash_sql([])).where(condition))
    _add_template(db_session, text=BLOCK)
    db_session.flush()
    after = db_session.scalar(
        select(embedding_hash_sql(TextQualityRepository(db_session).get_active_rules())).where(condition)
    )

    assert before != after
    assert len(after) == 32


# ==========================================
# DRY RUN
# ==========================================


def test_dry_run_counts_the_affected_documents_and_samples_them(db_session, generate_archive_doc) -> None:
    generate_archive_doc(original_title="Registros Fotográficos - Rua A")
    generate_archive_doc(original_title="Registros Fotográficos - Rua B", scope_content=BLOCK)
    generate_archive_doc(original_title="Rua sem prefixo")
    db_session.flush()

    report = TextQualityRepository(db_session).dry_run(
        [ExcerptRule(matchers=("Registros Fotográficos -",))], sample_limit=5
    )

    assert report.documents_affected == 2
    assert report.documents_scanned == 3
    assert all(sample.column == "original_title" for sample in report.samples)
    assert all(sample.modified_text.strip() == sample.modified_text for sample in report.samples)


def test_dry_run_reports_nothing_when_the_excerpt_does_not_match(db_session, generate_archive_doc) -> None:
    generate_archive_doc(original_title="Rua sem prefixo")
    db_session.flush()

    report = TextQualityRepository(db_session).dry_run([ExcerptRule(matchers=("inexistente",))])

    assert report.documents_affected == 0
    assert report.samples == []


def test_dry_run_counts_whitespace_variants_of_the_same_excerpt(db_session, generate_archive_doc) -> None:
    """The document text is normalized before matching, so extra spaces do not hide it."""
    generate_archive_doc(scope_content="Bloco   repetido com    espaços irregulares no meio do texto")
    db_session.flush()

    report = TextQualityRepository(db_session).dry_run(
        [ExcerptRule(matchers=("Bloco repetido com espaços irregulares no meio do texto",))]
    )

    assert report.documents_affected == 1


# ==========================================
# CATALOG PERSISTENCE
# ==========================================


def test_suggestions_are_idempotent_and_never_created_as_active(repo: TextQualityRepository, db_session) -> None:
    candidate = SuggestionCandidate(text=BLOCK, occurrence_count=10, sample_document_ids=["doc-1"])

    first = repo.upsert_suggestions([candidate])
    second = repo.upsert_suggestions(
        [SuggestionCandidate(text=BLOCK, occurrence_count=25, sample_document_ids=["doc-2"])]
    )

    rows = db_session.query(DomainTextTemplate).all()
    assert first == 1
    assert second == 1
    assert len(rows) == 1
    assert rows[0].status == "SUGGESTED"
    assert rows[0].source == "SUGGESTED"
    assert rows[0].is_active is False
    assert rows[0].occurrence_count == 25
    # Nothing reaches the AI before a human approves it.
    assert repo.get_active_rules() == []


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_suggestion_never_overwrites_a_human_decision(repo: TextQualityRepository, db_session, status: str) -> None:
    row = _add_template(db_session, text=BLOCK, status=status, is_active=False, occurrence_count=3)
    db_session.flush()

    repo.upsert_suggestions([SuggestionCandidate(text=BLOCK, occurrence_count=99, sample_document_ids=["doc-9"])])

    db_session.refresh(row)
    assert row.status == status
    assert row.occurrence_count == 3


def test_create_template_is_born_approved_and_normalized(repo: TextQualityRepository) -> None:
    template = repo.create_template(
        TemplateCreateCommand(text="  Bloco   repetido ", variants=["  Variante  "], created_by="ana")
    )

    assert template.status == "APPROVED"
    assert template.text == "Bloco repetido"
    assert template.variants == ["Variante"]
    assert template.created_by == "ana"


def test_update_can_approve_and_correct(repo: TextQualityRepository, db_session) -> None:
    row = _add_template(db_session, text=BLOCK, status="SUGGESTED", is_active=False)
    db_session.flush()

    updated = repo.update_template(
        row.template_id,
        TemplateUpdateCommand(status="APPROVED", is_active=True, replacement="", changed_by="ana"),
    )

    assert updated is not None
    assert updated.status == "APPROVED"
    assert updated.is_active is True
    assert updated.created_by == "ana"


def test_refresh_occurrence_count_stores_the_measured_evidence(repo: TextQualityRepository, db_session) -> None:
    row = _add_template(db_session, text=BLOCK)
    db_session.flush()

    refreshed = repo.refresh_occurrence_count(row.template_id, 2467)

    assert refreshed is not None
    assert refreshed.occurrence_count == 2467


def test_list_templates_filters_by_status_and_activity(repo: TextQualityRepository, db_session) -> None:
    _add_template(db_session, text="um trecho qualquer", status="APPROVED", is_active=True)
    _add_template(db_session, text="outro trecho", status="SUGGESTED", is_active=False)
    _add_template(db_session, text="terceiro trecho", status="REJECTED", is_active=False)
    db_session.flush()

    assert len(repo.list_templates()) == 3
    assert [template.status for template in repo.list_templates(status="SUGGESTED")] == ["SUGGESTED"]
    assert len(repo.list_templates(only_active=True)) == 1


# ==========================================
# RETROACTIVE EFFECT
# ==========================================


def test_find_documents_with_excerpt_normalizes_before_matching(
    repo: TextQualityRepository, generate_archive_doc
) -> None:
    spaced = generate_archive_doc(original_title="Registros   Fotográficos  -  Rua A")
    generate_archive_doc(original_title="Rua B")

    found = repo.find_documents_with_excerpt(["Registros Fotográficos -"])

    assert found == [spaced.description_id]


def test_requeue_removes_only_the_given_stamps(repo: TextQualityRepository, generate_archive_doc) -> None:
    doc = generate_archive_doc(
        original_title="Rua A",
        execution_log={"worker_ner_v2": "DONE", "worker_embedding_v1": "abc", "thumbnail": "True"},
    )

    changed = repo.requeue_documents([doc.description_id], ["worker_ner_v2", "worker_quality_validator_v1"])

    assert changed == 1
    assert doc.execution_log == {"worker_embedding_v1": "abc", "thumbnail": "True"}


def test_requeue_handles_a_document_without_a_log(repo: TextQualityRepository, generate_archive_doc) -> None:
    doc = generate_archive_doc(original_title="Rua B", execution_log=None)

    assert repo.requeue_documents([doc.description_id], ["worker_ner_v2"]) == 1
    assert doc.execution_log == {}


def test_requeue_without_keys_or_ids_is_a_noop(repo: TextQualityRepository, generate_archive_doc) -> None:
    doc = generate_archive_doc(original_title="Rua C", execution_log={"worker_ner_v2": "DONE"})

    assert repo.requeue_documents([], ["worker_ner_v2"]) == 0
    assert repo.requeue_documents([doc.description_id], []) == 0


def test_iter_text_columns_streams_every_requested_column(repo: TextQualityRepository, generate_archive_doc) -> None:
    doc = generate_archive_doc(original_title="Rua D", scope_content="Escopo", document_date=date(1954, 3, 15))

    rows = list(repo.iter_text_columns(["original_title", "scope_content", "final_title"], batch_size=1))

    assert ("original_title", "Rua D") in {(column, value) for _id, column, value in rows}
    assert all(description_id == doc.description_id for description_id, _column, _value in rows)


# ==========================================
# SCOPE PER CONSUMER (measured decision)
# ==========================================


def test_active_rules_are_filtered_by_scope(repo: TextQualityRepository, db_session) -> None:
    _add_template(db_session, text="Registros Fotográficos -", scope=["TITLE"])
    _add_template(db_session, text=BLOCK, scope=["EMBEDDING", "NER"])
    db_session.flush()

    titles = [rule.matchers[0] for rule in repo.get_active_rules("TITLE")]
    embeddings = [rule.matchers[0] for rule in repo.get_active_rules("EMBEDDING")]
    everything = [rule.matchers[0] for rule in repo.get_active_rules()]

    assert titles == ["Registros Fotográficos -"]
    assert embeddings == [BLOCK]
    assert set(everything) == {BLOCK, "Registros Fotográficos -"}


def test_a_title_only_excerpt_never_reaches_the_embedded_text(
    repo: TextQualityRepository, db_session, generate_archive_doc
) -> None:
    """
    Regression for the measured finding: subtracting the repeated title prefix from the
    embedded text made Hit@10 fall from 0.562 to 0.500, while the title suggestion needs
    exactly that subtraction.
    """
    doc = generate_archive_doc(original_title="Registros Fotográficos - Rua A", scope_content=BLOCK)
    _add_template(db_session, text="Registros Fotográficos -", scope=["TITLE"])
    _add_template(db_session, text=BLOCK, scope=["EMBEDDING"])
    db_session.flush()
    condition = ArchiveDocument.description_id == doc.description_id

    embedded = db_session.scalar(select(embedding_text_sql(repo.get_active_rules("EMBEDDING"))).where(condition))
    suggested = db_session.scalar(select(effective_title_sql(repo.get_active_rules("TITLE"))).where(condition))

    assert embedded == "Registros Fotográficos - Rua A"
    assert suggested == "Rua A"


def test_the_scope_is_validated_by_the_database(repo: TextQualityRepository, db_session) -> None:
    """The check constraint keeps a typo from silently disabling an excerpt."""
    from sqlalchemy.exc import IntegrityError

    # ``_add_template`` flushes, and that is exactly where PostgreSQL must refuse the row.
    with pytest.raises(IntegrityError):
        _add_template(db_session, text="trecho qualquer com tamanho suficiente", scope=["EMBEDDINGS"])

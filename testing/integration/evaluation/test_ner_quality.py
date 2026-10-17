"""
Integration tests for the NER bench (issue #113).

The load-bearing one is the pin: the bench must read the text the worker reads. It is measured by
running the real worker with a fake engine and comparing what the worker handed to the model with
what the bench composes for the same document — including the URL stripping the NER worker does and
the approved excerpt the composition subtracts. A bench that composed the text in Python would
measure a text the worker never sees (principle IV).

The second rule these tests hold is that the bench writes nothing: it is a read of the collection and
the session is rolled back, so the counts on either side of a full run have to match.
"""

from __future__ import annotations

from collections import Counter
from typing import get_args

from sqlalchemy import func, select

from scrinalia.domains.archive.engines.NER import registry as ner_registry
from scrinalia.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveEntity,
    ArchiveReviewStatus,
    DomainStopwords,
    StopwordsScope,
)
from scrinalia.domains.archive.repository.text_quality_repo import TextQualityRepository
from scrinalia.domains.archive.schemas.entity_schema import ArchiveEntityDTO
from scrinalia.domains.archive.schemas.text_quality_schema import TemplateCreateCommand
from scrinalia.domains.archive.worker_stamp import NER
from scrinalia.domains.archive.workers.worker_ner import execute
from testing.evaluation.ner_quality import (
    ENTITY_TYPES,
    BenchConfig,
    LabelledRow,
    Mention,
    Truth,
    build_payload,
    read_candidates,
    read_composed_text,
    score_live,
    score_stored,
    stored_mentions,
    stored_producers,
    worker_scope_ids,
)

BLOCK = "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do Planejamento"
#: A URL in the middle of the title on purpose: the NER worker strips it before inference, and a
#: bench that forgot that step would compare two different strings.
TITLE = "Registros Fotográficos - Rua Izaac http://exemplo.invalido/x"


def labelled(description_id: str, terms: list[tuple[str, str]]) -> LabelledRow:
    return LabelledRow(
        description_id=description_id,
        truth=Truth(mentions=tuple(Mention(term=term, type=entity_type) for term, entity_type in terms)),
        needs_decision=False,
        note="",
    )


def add_entity(db_session, description_id: str, name: str, entity_type: str) -> ArchiveEntity:
    entity = ArchiveEntity(name=name, entity_type=entity_type)
    db_session.add(entity)
    db_session.flush()
    db_session.add(ArchiveDocumentEntity(description_id=description_id, entity_id=entity.entity_id))
    db_session.flush()
    return entity


def count_links(db_session) -> int:
    return int(db_session.scalar(select(func.count()).select_from(ArchiveDocumentEntity)) or 0)


# =============================================================================
# The pin: the bench reads what the worker reads
# =============================================================================


def test_the_bench_composes_the_same_text_the_worker_hands_the_engine(
    use_test_db,
    db_session,
    generate_archive_doc,
    mock_registry,
):
    """
    The pin of the pair, with an approved excerpt and a URL in the middle.

    Both details are load-bearing. Without the excerpt, a bench that forgot the catalog rules would
    still match; without the URL, a bench that forgot ``_clean_raw_text`` would still match. The two
    together mean the bench has to reproduce the worker's whole composition to pass.
    """
    generate_archive_doc(description_id="same1", original_title=TITLE, scope_content=BLOCK)
    TextQualityRepository(db_session).create_template(TemplateCreateCommand(text=BLOCK))

    MockClass = mock_registry(ner_registry)
    engine = MockClass.return_value
    engine.extract.return_value = [[ArchiveEntityDTO(name="Curitiba", entity_type="LOC")]]

    columns = ["original_title", "scope_content"]
    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore[arg-type]
        preset="preset_teste",  # type: ignore[arg-type]
        columns_to_extract=columns,
    )

    worker_text = engine.extract.call_args.args[0][0]
    bench_text = read_composed_text(db_session, ["same1"], columns)["same1"]

    assert "http" not in worker_text, "the worker strips URLs before inference"
    assert BLOCK not in worker_text, "the approved excerpt is subtracted from the composed text"
    assert bench_text == worker_text


def test_the_bench_reads_the_url_stripping_the_worker_applies(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """The cleaner on its own, without the pin's other half, so a regression names the right step."""
    generate_archive_doc(description_id="clean1", original_title=TITLE, scope_content=None)

    text = read_composed_text(db_session, ["clean1"], ["original_title"])["clean1"]

    assert text == "Registros Fotográficos - Rua Izaac"


# =============================================================================
# The scope: the worker's own document selection
# =============================================================================


def test_the_scope_excludes_a_human_approved_document(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """A document the worker will never read again cannot be scored against it."""
    generate_archive_doc(description_id="writable", original_title="Rua Izaac")
    generate_archive_doc(
        description_id="approved",
        original_title="Rua Izaac",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )

    in_scope = worker_scope_ids(db_session, ["writable", "approved"])

    assert in_scope == {"writable"}


def test_the_scope_keeps_a_document_whose_composed_text_is_empty(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """
    The scope predicate is the worker's own, and the empty-text rule lives *inside* its loop.

    ``original_title`` is NOT NULL, so the ``or_(column is not None)`` half of the selection can
    never exclude a document that exists: what keeps an empty description from the engine is the
    composed text being empty, which ``score_live`` mirrors. The stamp is deliberately **not** part
    of this predicate — it is a queue cursor, and the documents this producer already stamped are
    exactly the ones a bench has to score.
    """
    generate_archive_doc(description_id="blank", original_title="")

    assert worker_scope_ids(db_session, ["blank"]) == {"blank"}
    assert read_composed_text(db_session, ["blank"], ["original_title"])["blank"] == ""


# =============================================================================
# The stored mode
# =============================================================================


def test_the_stored_mode_reads_the_links_the_run_wrote(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    generate_archive_doc(description_id="stored1", original_title="Rua Izaac")
    add_entity(db_session, "stored1", "Curitiba", "LOC")
    add_entity(db_session, "stored1", "David Carneiro", "PER")

    scored = score_stored(db_session, [labelled("stored1", [("Curitiba", "LOC"), ("David Carneiro", "PER")])])

    assert scored[0].correct
    assert scored[0].extraction.mentions == (
        Mention(term="Curitiba", type="LOC"),
        Mention(term="David Carneiro", type="PER"),
    )


def test_the_stored_mode_reports_a_document_nothing_was_written_for_as_an_empty_extraction(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """
    The limitation, pinned rather than described: no link is both "the run found nothing" and "no
    run reached this document", and the bench can only read the links.
    """
    generate_archive_doc(description_id="untouched", original_title="Rua Izaac")

    scored = score_stored(db_session, [labelled("untouched", [("Curitiba", "LOC")])])

    assert scored[0].extraction.mentions == ()
    assert not scored[0].correct


def test_the_stored_mode_names_the_producer_the_documents_carry(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """The honest substitute for the boundary breakdown in this mode: whose output was read."""
    document = generate_archive_doc(description_id="stamped", original_title="Rua Izaac")
    document.execution_log = NER.mark_value(document.execution_log, "identidade-do-ultimo-run")
    db_session.flush()
    generate_archive_doc(description_id="unstamped", original_title="Rua Izaac")

    producers = stored_producers(db_session, ["stamped", "unstamped"])

    assert producers == Counter({"identidade-do-ultimo-run": 1, "(sem carimbo)": 1})


def test_the_stored_mentions_are_grouped_by_document(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    generate_archive_doc(description_id="grouped", original_title="Rua Izaac")
    generate_archive_doc(description_id="other", original_title="Rua Izaac")
    add_entity(db_session, "grouped", "Curitiba", "LOC")
    add_entity(db_session, "other", "Paraná", "LOC")

    mentions = stored_mentions(db_session, ["grouped", "other"])

    assert mentions["grouped"] == [Mention(term="Curitiba", type="LOC")]
    assert mentions["other"] == [Mention(term="Paraná", type="LOC")]


# =============================================================================
# The live mode
# =============================================================================


def test_the_live_mode_extracts_through_the_engine(
    use_test_db,
    db_session,
    generate_archive_doc,
    mock_registry,
):
    """The engine is asked once, in batch, with the composed text — as ``execute`` does it."""
    generate_archive_doc(description_id="live1", original_title="Rua Izaac", scope_content="Curitiba")

    MockClass = mock_registry(ner_registry)
    engine = MockClass.return_value
    engine.extract.return_value = [[ArchiveEntityDTO(name="Curitiba", entity_type="LOC")]]

    config = BenchConfig(engine="motor_fake", preset="preset_teste", columns=("original_title", "scope_content"))
    scored, _seconds = score_live(db_session, config, [labelled("live1", [("Curitiba", "LOC")])], engine=engine)

    assert scored[0].correct
    assert engine.extract.call_args.args[0] == ["Rua Izaac. Curitiba"]


def test_the_live_mode_never_asks_the_engine_about_a_document_with_no_text(
    use_test_db,
    db_session,
    generate_archive_doc,
    mock_registry,
):
    """
    The worker's empty-text rule, mirrored: a document with nothing to read is skipped, not asked.

    The extraction is then empty rather than missing, which is the difference between "the model
    found nothing" and "the model was never consulted" — and the bench must not blur them.
    """
    generate_archive_doc(description_id="silent", original_title="")

    MockClass = mock_registry(ner_registry)
    engine = MockClass.return_value
    engine.extract.return_value = []

    config = BenchConfig(engine="motor_fake", preset="preset_teste", columns=("original_title",))
    scored, _seconds = score_live(db_session, config, [labelled("silent", [("Curitiba", "LOC")])], engine=engine)

    engine.extract.assert_not_called()
    assert scored[0].extraction.mentions == ()


def test_the_live_mode_filters_the_blacklist_the_worker_filters(
    use_test_db,
    db_session,
    generate_archive_doc,
    mock_registry,
):
    """A term a curator banned is dropped after inference, exactly where the worker drops it."""
    generate_archive_doc(description_id="banned", original_title="Rua Izaac", scope_content="Curitiba")
    db_session.add(DomainStopwords(word="Curitiba", word_scope=StopwordsScope.ENTITY))
    db_session.flush()

    MockClass = mock_registry(ner_registry)
    engine = MockClass.return_value
    engine.extract.return_value = [[ArchiveEntityDTO(name="Curitiba", entity_type="LOC")]]

    config = BenchConfig(engine="motor_fake", preset="preset_teste", columns=("original_title", "scope_content"))
    scored, _seconds = score_live(db_session, config, [labelled("banned", [("Curitiba", "LOC")])], engine=engine)

    assert scored[0].extraction.mentions == ()
    assert not scored[0].correct


# =============================================================================
# The proposal
# =============================================================================


def test_the_proposal_draws_from_the_stored_links_and_from_the_documents_with_none(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """
    Both halves of the sample, because a sample drawn only from the model's output cannot see what
    the model missed — the same argument the validator bench makes for its clean bucket.
    """
    generate_archive_doc(description_id="with_entity", original_title="Rua Izaac")
    generate_archive_doc(description_id="empty_doc", original_title="Rua Izaac")
    add_entity(db_session, "with_entity", "Curitiba", "LOC")

    candidates = read_candidates(db_session, per_type=10, empty_rows=10, seed="seed")

    by_id = {candidate.description_id: candidate for candidate in candidates}
    assert by_id["with_entity"].proposed_by == "LOC"
    assert by_id["with_entity"].stored == (Mention(term="Curitiba", type="LOC"),)
    assert by_id["empty_doc"].proposed_by == "(sem tipo)"
    assert by_id["empty_doc"].stored == ()


def test_the_proposal_leaves_expected_empty_and_fills_proposed(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """
    The shape that carries the anchoring bias and the shape that defuses it.

    ``proposed`` is the model's own answer and is what the curator corrects; ``expected`` is empty on
    every row, so a set scored without a correction scores nothing instead of scoring the model
    against itself.
    """
    generate_archive_doc(description_id="anchor", original_title="Rua Izaac")
    add_entity(db_session, "anchor", "Curitiba", "LOC")

    candidates = read_candidates(db_session, per_type=10, empty_rows=10, seed="seed")
    payload = build_payload(candidates, seed="seed", per_type=10, empty_rows=10)

    assert payload["pairs"], "the collection has one candidate and it must be proposed"
    assert all(pair["expected"] is None for pair in payload["pairs"])
    assert payload["pairs"][0]["proposed"] == [{"term": "Curitiba", "type": "LOC"}]
    assert payload["status"].startswith("draft")
    assert any("viés" in line.lower() for line in payload["instructions_for_the_curator"])


def test_the_sampling_is_reproducible_and_recorded(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    for index in range(6):
        generate_archive_doc(description_id=f"rep{index}", original_title="Rua Izaac")
        add_entity(db_session, f"rep{index}", f"Curitiba {index}", "LOC")

    first = [candidate.description_id for candidate in read_candidates(db_session, 2, 0, "seed")]
    second = [candidate.description_id for candidate in read_candidates(db_session, 2, 0, "seed")]
    other = [candidate.description_id for candidate in read_candidates(db_session, 2, 0, "other-seed")]

    assert first == second
    assert first != other


# =============================================================================
# Nothing is written
# =============================================================================


def test_a_full_score_leaves_the_collection_untouched(
    use_test_db,
    db_session,
    generate_archive_doc,
    mock_registry,
):
    """
    The bench reads the collection and rolls back; it is not a run.

    Asserted on the links and on the session's own pending state, because a bench that committed
    would be indistinguishable from a worker run and would rewrite the very output it measures.
    """
    generate_archive_doc(description_id="untouched_by_the_bench", original_title="Rua Izaac")
    add_entity(db_session, "untouched_by_the_bench", "Curitiba", "LOC")
    before = count_links(db_session)
    documents_before = int(db_session.scalar(select(func.count()).select_from(ArchiveDocument)) or 0)

    MockClass = mock_registry(ner_registry)
    engine = MockClass.return_value
    engine.extract.return_value = [[ArchiveEntityDTO(name="Curitiba", entity_type="LOC")]]

    rows = [labelled("untouched_by_the_bench", [("Curitiba", "LOC")])]
    config = BenchConfig(engine="motor_fake", preset="preset_teste", columns=("original_title",))
    score_stored(db_session, rows)
    score_live(db_session, config, rows, engine=engine)
    read_candidates(db_session, per_type=5, empty_rows=5, seed="seed")
    stored_producers(db_session, ["untouched_by_the_bench"])

    assert count_links(db_session) == before
    assert int(db_session.scalar(select(func.count()).select_from(ArchiveDocument)) or 0) == documents_before
    # ``IdentitySet`` does not compare equal to a plain ``set``, so the length is the assertion.
    assert len(db_session.new) == 0
    assert len(db_session.dirty) == 0


def test_the_bench_reads_the_engine_contract_the_registry_declares() -> None:
    """
    The types the metric knows are the types the DTO can return.

    A new entity type would otherwise be counted under a label the engine never produces, or dropped
    from the table while still being extracted.
    """
    declared = get_args(ArchiveEntityDTO.model_fields["entity_type"].annotation)

    assert set(ENTITY_TYPES) == set(declared)

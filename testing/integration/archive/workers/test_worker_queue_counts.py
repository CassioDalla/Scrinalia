"""The panel's numbers must be the worker's own predicate, not a second definition of it.

Each test seeds a small collection that separates "pending" from "already handled" and asserts the
counter through the same function the operations screen calls. The refactor that extracted the
predicate from every ``execute`` is only worth it if these numbers keep matching the worker.
"""

from scrinalia.core.runner_config import MacroCategoryRunnerConfig, NerRunnerConfig, TypologyRunnerConfig
from scrinalia.domains.archive.models import (
    ArchiveMacroCategory,
    ArchiveReviewStatus,
    ArchiveTag,
)
from scrinalia.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from scrinalia.domains.archive.ports.staging_source import StagingRecord
from scrinalia.domains.archive.repository import TypologyRepository
from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository
from scrinalia.domains.archive.repository.tag_repo import TagRepository
from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO
from scrinalia.domains.archive.worker_stamp import (
    EMBEDDING,
    MACRO_CATEGORY,
    NER,
    QUALITY_VALIDATOR,
    THUMBNAIL_FAILED,
    TYPOLOGY,
)
from scrinalia.domains.archive.workers import (
    worker_archive_transfer,
    worker_cleaning_regex,
    worker_embedding,
    worker_macro_category,
    worker_ner,
    worker_quality_validator,
    worker_resolve_tag_entity_conflict,
    worker_thumbnail,
    worker_typology,
)
from scrinalia.domains.archive.workers.worker_quality_validator import (
    DEFAULT_LLM_CONFIDENCE,
    DEFAULT_REPEAT_THRESHOLD,
)
from scrinalia.domains.staging.models import StagingDocument


def test_ner_counts_unstamped_writable_documents(db_session, generate_archive_doc) -> None:
    identity = worker_ner.producer_identity(
        engine_name="spacy_ner",
        preset="gpu",
        columns_to_extract=list(NerRunnerConfig().columns_to_extract),
        engine_kwargs={},
    )
    generate_archive_doc(original_title="Pendente")
    generate_archive_doc(original_title="Feito", execution_log={NER.key: identity})
    generate_archive_doc(original_title="Aprovado", review_status=ArchiveReviewStatus.HUMAN_APPROVED)

    assert worker_ner.count_pending(db_session) == 1
    # A stamp from another producer is pending again: the queue is keyed on what produced it.
    generate_archive_doc(original_title="De outro modelo", execution_log={NER.key: "DONE"})
    assert worker_ner.count_pending(db_session) == 2


def test_typology_counts_by_the_stamp_and_not_by_the_answer(
    db_session, generate_archive_doc, generate_typology
) -> None:
    """
    The stamp is the only gate on the answer side (issue #117).

    ``typology_id IS NULL`` used to be ANDed into the predicate, and it made the identity inert: a
    document that already carried a typology never came back, so nothing the identity signs — floor,
    model, columns or label set — reached the documents the last run had classified.
    """
    typology = generate_typology()
    config = TypologyRunnerConfig()

    def identity_at(threshold: float) -> str:
        return worker_typology.producer_identity(
            engine_name="deberta_typology",
            preset="cpu_local",
            columns_to_classify=list(config.columns_to_classify),
            confidence_threshold=threshold,
            typologies=TypologyRepository(db_session).get_active_typologies(),
            engine_kwargs={},
        )

    generate_archive_doc(original_title="Sem tipologia")
    generate_archive_doc(original_title="Com tipologia", typology_id=typology.typology_id)
    generate_archive_doc(original_title="Do produtor atual", execution_log={TYPOLOGY.key: identity_at(0.40)})
    generate_archive_doc(original_title="Carimbo antigo", execution_log={TYPOLOGY.key: "DONE"})
    generate_archive_doc(original_title="Aprovado", review_status=ArchiveReviewStatus.HUMAN_APPROVED)

    # Everything ai-writable except the document the current producer settled: the one carrying a
    # typology is pending again because nothing stamped it, which is the whole point of the change.
    assert worker_typology.count_pending(db_session) == 3

    # A simulated change of floor moves the number without writing anything: the document the
    # 0.40 producer settled is pending under the 0.55 one. This is what the panel must show.
    assert worker_typology.count_pending(db_session, confidence_threshold=0.55) == 4

    # Governance is untouched: a human approval still keeps the document out of every queue.
    assert worker_typology.count_pending(db_session, force=True) == 4


def test_quality_validator_counts_and_force_widens_it(db_session, generate_archive_doc) -> None:
    identity = worker_quality_validator.producer_identity(
        db_session,
        repeat_threshold=DEFAULT_REPEAT_THRESHOLD,
        llm_confidence=DEFAULT_LLM_CONFIDENCE,
        engine_kwargs={},
    )
    generate_archive_doc()
    generate_archive_doc(execution_log={QUALITY_VALIDATOR.key: identity})

    assert worker_quality_validator.count_pending(db_session) == 1
    assert worker_quality_validator.count_pending(db_session, force=True) == 2


def test_embedding_counts_unstamped_and_skips_rejected(db_session, generate_archive_doc) -> None:
    generate_archive_doc(scope_content="um texto qualquer")
    generate_archive_doc(scope_content="outro texto", review_status=ArchiveReviewStatus.REJECTED)

    assert worker_embedding.count_pending(db_session) == 1
    assert worker_embedding.count_pending(db_session, force=True) == 1


def test_embedding_requeues_when_the_stamp_is_not_the_text_hash(db_session, generate_archive_doc) -> None:
    """A stale stamp — the shape a human edit leaves behind — is pending again."""
    generate_archive_doc(scope_content="texto", execution_log={EMBEDDING.key: "hash de outro texto"})

    assert worker_embedding.count_pending(db_session) == 1


def test_thumbnail_counts_by_storage_uri_and_failure_mark(db_session, generate_archive_doc) -> None:
    generate_archive_doc(original_thumbnail_url="http://exemplo/1.jpg")
    generate_archive_doc(original_thumbnail_url="http://exemplo/2.jpg", storage_thumbnail_uri="thumbnails/2.jpg")
    generate_archive_doc(original_thumbnail_url="http://exemplo/3.jpg", execution_log={THUMBNAIL_FAILED.key: "True"})
    generate_archive_doc()

    assert worker_thumbnail.count_pending(db_session) == 1
    assert worker_thumbnail.count_processed(db_session) == 1
    assert worker_thumbnail.count_failed(db_session) == 1


def test_macro_category_counts_orphan_tags_and_the_fingerprint_matters(db_session) -> None:
    category = ArchiveMacroCategory(name="Urbanismo", is_active=True)
    db_session.add(category)
    db_session.flush()

    categories = TagRepository(db_session).get_active_macro_categories()
    identity = worker_macro_category.producer_identity(
        engine_name="deberta_typology",
        preset="cpu_local",
        categories_map=categories,
        confidence_threshold=MacroCategoryRunnerConfig().confidence_threshold,
        engine_kwargs={},
    )

    db_session.add(ArchiveTag(name="sem-gaveta"))
    db_session.add(ArchiveTag(name="ja-classificada", execution_log={MACRO_CATEGORY.key: identity}))
    db_session.add(ArchiveTag(name="vocabulario-mudou", execution_log={MACRO_CATEGORY.key: "fingerprint antigo"}))
    db_session.add(ArchiveTag(name="curada", macro_category_id=category.category_id))
    db_session.flush()

    assert worker_macro_category.count_pending(db_session) == 2
    assert worker_macro_category.count_pending(db_session, force=True) == 3
    # The floor is part of the identity too: raising it makes the settled tag pending again.
    assert worker_macro_category.count_pending(db_session, confidence_threshold=0.70) == 3


def test_cleaning_counts_per_active_rewrite_rule_only(db_session, generate_archive_doc) -> None:
    generate_archive_doc(scope_content="texto com aaaaa dentro")
    repository = CleaningRepository(db_session)
    repository.create_rule(
        CleaningRuleCreateDTO(
            rule_name="reescreve",
            target_column="scope_content",
            regex_pattern="aaaaa",
            replacement_string="",
            rule_kind="REWRITE",
        )
    )
    repository.create_rule(
        CleaningRuleCreateDTO(
            rule_name="apenas sinaliza",
            target_column="scope_content",
            regex_pattern="texto",
            replacement_string="",
            rule_kind="VALIDATE",
        )
    )
    db_session.flush()

    assert worker_cleaning_regex.count_pending(db_session) == 1


def test_transfer_counts_staging_records_whose_cdc_key_moved(db_session, generate_archive_doc) -> None:
    db_session.add(StagingDocument(description_id="stg-novo", raw_content_hash="h1", title="Novo"))
    db_session.add(StagingDocument(description_id="stg-igual", raw_content_hash="h2", title="Igual"))
    db_session.add(StagingDocument(description_id="stg-aprovado", raw_content_hash="h3", title="Aprovado"))
    db_session.flush()

    # The archive already carries the parsed hash of one record, so it is not pending.
    equal_record = StagingRecord.model_validate(db_session.get(StagingDocument, "stg-igual"))
    generate_archive_doc(description_id="stg-igual", staging_content_hash=equal_record.parsed_content_hash())
    # A different hash on a HUMAN_APPROVED document is not pending: the upsert refuses to touch it.
    generate_archive_doc(
        description_id="stg-aprovado",
        staging_content_hash="hash antigo",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )

    assert worker_archive_transfer.count_pending(db_session) == 1


def test_conflict_judge_counts_what_was_already_judged(db_session) -> None:
    """The pending queue is not measurable cheaply; what is measured is the decision ledger."""
    db_session.add(
        ArchiveAIReviewQueue(
            anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
            status=ArchiveReviewStatus.NEEDS_REVIEW,
            context_payload={"tag_id": 1, "entity_id": 2},
        )
    )
    db_session.add(
        ArchiveAIReviewQueue(
            anomaly_type=AnomalyType.SUBJECT_LOW_CONFIDENCE,
            status=ArchiveReviewStatus.NEEDS_REVIEW,
            context_payload={"tag_id": 3},
        )
    )
    db_session.flush()

    assert worker_resolve_tag_entity_conflict.count_judged(db_session) == 1

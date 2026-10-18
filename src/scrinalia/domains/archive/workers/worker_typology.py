from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql.elements import ColumnElement

from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.runner_config import TypologyRunnerConfig
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.archive.domain.vocabulary import label_set_fingerprint
from scrinalia.domains.archive.engines.base import TypologyEngine
from scrinalia.domains.archive.engines.classification.registry import (
    EngineName,
    PresetName,
    describe_config,
    get_engine,
)
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from scrinalia.domains.archive.repository import TypologyRepository
from scrinalia.domains.archive.repository.governance import ai_writable_documents
from scrinalia.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    composed_text_sql,
)
from scrinalia.domains.archive.worker_stamp import TYPOLOGY, identity_stamp_conditions, producer_fingerprint
from scrinalia.domains.archive.workers.run_budget import RunBudget


def resolved_parameters(
    config: TypologyRunnerConfig | None,
    columns_to_classify: list[str] | None,
    confidence_threshold: float | None,
) -> tuple[list[str], float]:
    """
    The two business parameters a run really uses, resolved once for ``execute`` and the panel.

    They are resolved here for the same reason the predicate is shared: the panel has to count the
    queue under the configuration it is about to run, and a second resolution could disagree about
    what "the threshold" is — which is exactly the disagreement that leaves a measured value
    unreachable.
    """
    resolved = config or TypologyRunnerConfig()
    columns = list(columns_to_classify or resolved.columns_to_classify)
    threshold = resolved.confidence_threshold if confidence_threshold is None else float(confidence_threshold)
    return columns, threshold


def producer_identity(
    *,
    engine_name: EngineName,
    preset: PresetName | None,
    columns_to_classify: list[str],
    confidence_threshold: float,
    typologies: dict[str, int],
    engine_kwargs: dict,
) -> str:
    """
    Identity of the classifier that produced the typology of a document.

    Three changes re-queue a classified document by themselves, and they are different facts: the
    **label set** it was read against (a typology added, renamed or retired), the model that read it,
    and the parameters that decide the answer (the columns and the confidence floor). All of them
    compose this one value.

    The label set comes from ``get_active_typologies()``, whose ``{name: id}`` shape is exactly what
    ``label_set_fingerprint`` takes — the same hash the subject axis signs. Without it the promise
    above was false in both directions: the catalogue was not signed *and* the queue ignored the
    signature, so a catalogue edit reached no document that already carried a typology (measured on
    2026-10-17; the numbers are in #117).
    """
    config = describe_config(engine_name, preset, **engine_kwargs)
    return producer_fingerprint(
        axis="classification",
        engine_name=engine_name,
        preset=preset,
        engine_config=config,
        worker_options={
            "columns_to_classify": columns_to_classify,
            "confidence_threshold": confidence_threshold,
            "labels": label_set_fingerprint(typologies),
        },
    )


def pending_conditions(
    columns_to_classify: list[str],
    producer: str,
    force: bool = False,
) -> list[ColumnElement[bool]]:
    """
    Predicate of the typology queue, shared by ``execute`` and the operations panel.

    The gate is the **stamp**, not the answer. This used to AND a third clause,
    ``typology_id IS NULL``, and it made the producer identity inert: a document that already carried
    a typology never went back to the classifier, so changing the floor, the model, the columns or
    the label set reached none of the documents the last run had classified. Measured on
    ``memoriacuritibana`` on 2026-10-17, ``count_pending`` answered 4,205 under two floors, two column
    sets and two presets — 4,813 ai-writable documents minus the 608 that already carried a typology,
    exactly.

    The clause also duplicated the two gates that remain: a human verdict is ``ai_writable_documents``
    (principle VII), and "do not redo the work" is the stamp. A document a human approved is still
    out of reach here. ``force`` widens the queue to everything ai-writable, and the worker advances
    by cursor so a forced run still ends.
    """
    filters_columns = [getattr(ArchiveDocument, col).is_not(None) for col in columns_to_classify]
    conditions: list[ColumnElement[bool]] = [
        ai_writable_documents(),
        or_(*filters_columns),
    ]
    conditions.extend(identity_stamp_conditions(ArchiveDocument.execution_log, TYPOLOGY, producer, force=force))
    return conditions


def count_pending(
    db: Session,
    columns_to_classify: list[str] | None = None,
    config: TypologyRunnerConfig | None = None,
    confidence_threshold: float | None = None,
    force: bool = False,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName | None = "cpu_local",
    **engine_kwargs,
) -> int:
    """Documents the next typology run would classify, under the identity it would write."""
    columns, threshold = resolved_parameters(config, columns_to_classify, confidence_threshold)
    identity = producer_identity(
        engine_name=engine_name,
        preset=preset,
        columns_to_classify=columns,
        confidence_threshold=threshold,
        typologies=TypologyRepository(db).get_active_typologies(),
        engine_kwargs=engine_kwargs,
    )
    stmt = select(func.count()).select_from(ArchiveDocument).where(*pending_conditions(columns, identity, force=force))
    return int(db.scalar(stmt) or 0)


def execute(
    db: Session,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName = "cpu_local",
    db_batch_size: int = 64,
    columns_to_classify: list[str] | None = None,
    config: TypologyRunnerConfig | None = None,
    confidence_threshold: float | None = None,
    force: bool = False,
    limit: int | None = None,
    **engine_kwargs,
) -> None:
    """
    Orchestrator of the Document Typology Classification pipeline.

    Continuously fetches, in batches, the documents in the database that have not
    yet been processed by this routine (checking the JSON column `execution_log`).
    Dynamically concatenates the requested columns to form the context and uses
    an Artificial Intelligence engine injected via the Registry to classify
    the document into one of the active typologies in the system.

    If the inference confidence (confidence score) is above the threshold, it links the
    `typology_id` to the document. Regardless of the classification success,
    the document is stamped with the **identity of the classifier** so it does not enter a
    loop — and so that a different engine, preset or threshold puts it back in the queue,
    which is what makes a classification revisable. A human decision still wins: an approved
    document is out of reach of the plain queue, and only ``force`` re-reads it.

    The processing is shielded with memory protection (expunge_all) after each completed
    transaction, and the loop advances by a ``description_id`` cursor: the stamp is what leaves
    the queue in a plain run, but a ``force`` run ignores the stamp, and without the cursor it
    would refetch the same documents forever.

    Args:
        db (Session): Database session.
        engine_name (EngineName, optional): Identifier of the AI engine registered in the
            system (e.g. "deberta_typology"). Default is "deberta_typology".
        preset (PresetName, optional): Name of a pre-configuration (e.g. "cpu_local", "gpu_cloud")
            that defines the engine's default hyperparameters. Default is "cpu_local".
        db_batch_size (int, optional): Number of documents fetched from the database
            and saved per transaction (commit). Default is 64.
        columns_to_classify (list[str] | None, optional): List with the exact names of the
            `ArchiveDocument` model columns that will form the text read by the AI. If `None`,
            it internally uses `["original_title"]`.
        config (TypologyRunnerConfig | None, optional): Business thresholds; when `None`, the
            defaults are used. The declared ``confidence_threshold`` wins over it, so a value
            measured by the bench can be tried without editing code.
        confidence_threshold (float | None, optional): Confidence floor to link a typology.
            `None` uses the one in ``config`` (0.40 by default).
        force (bool, optional): When ``True``, ignores the producer identity and re-reads every
            ai-writable document once, which is the way back from a prompt, a vocabulary table or
            a rule a hash cannot see. Default is ``False``.
        limit (int | None, optional): Cap on the documents this run touches, so a trial costs N
            documents instead of the collection. Not persisted. Default is ``None``.
        **engine_kwargs: Arbitrary arguments that will be forwarded directly to
            the AI engine constructor, overriding the `preset` configurations
            (e.g. `device="cuda:0"`, `max_length=256`).

    Raises:
        Exception: If there is a catastrophic failure instantiating the processing engine
            (e.g. model not found, machine out of memory).

    Returns:
        None. The process runs until the database queue is emptied.
    """

    logger.info(
        f"🚀 Starting the Typology Classifier Worker (Engine: {engine_name} | Preset: {preset} | Force: {force})"
    )

    config = config or TypologyRunnerConfig()
    columns_to_classify, confidence_threshold = resolved_parameters(config, columns_to_classify, confidence_threshold)

    repository = TypologyRepository(db)
    uow = UnitOfWork(db)

    try:
        logger.info("Loading Processing Engine...")
        engine: TypologyEngine = get_engine(engine_name=engine_name, preset=preset, **engine_kwargs)
    except Exception as e:
        logger.error(f"❌ Error loading the model: {e}")
        raise

    typologies_map = repository.get_active_typologies()
    if not typologies_map:
        logger.warning("⚠️ No typology registered in the database. Aborting Classification.")
        return

    identity = producer_identity(
        engine_name=engine_name,
        preset=preset,
        columns_to_classify=columns_to_classify,
        confidence_threshold=confidence_threshold,
        typologies=typologies_map,
        engine_kwargs=engine_kwargs,
    )
    logger.info(f"🔖 Producer identity: {identity[:12]} (threshold {confidence_threshold:.2f})")

    candidate_labels = list(typologies_map.keys())
    logger.info(f"📂 {len(candidate_labels)} typologies loaded.")

    # Fetches the ArchiveDocument class attributes at runtime
    where_cond = pending_conditions(columns_to_classify, identity, force=force)

    query_count = select(func.count()).select_from(ArchiveDocument).where(*where_cond)
    total_documents = db.scalar(query_count)

    if not total_documents:
        logger.info("✨ No pending document found. Finishing.")
        return

    logger.info(f"🔍 Found {total_documents} documents to classify.")

    # Catalog excerpts approved by the archivist are subtracted before classifying: the
    # shared boilerplate is what pulled every document towards the same typology.
    rules = TextQualityRepository(db).get_active_rules("NER")
    text_expression = composed_text_sql(columns_to_classify, rules, separator=". ")
    logger.info(f"🧹 {len(rules)} approved excerpt(s) will be kept out of the classified text.")

    total_processed = 0
    last_id = ""
    budget = RunBudget(limit)

    while True:
        try:
            query = (
                select(ArchiveDocument, text_expression.label("effective_text"))
                .where(*where_cond, ArchiveDocument.description_id > last_id)
                .order_by(ArchiveDocument.description_id)
                .limit(budget.batch_size(db_batch_size))
            )

            batch_rows = db.execute(query).all()

            if not batch_rows:
                break

            last_id = batch_rows[-1][0].description_id
            budget.spend(len(batch_rows))

            texts_buffer = []
            valid_docs = []

            # Text preparation (already composed by PostgreSQL)
            for doc, raw_text in batch_rows:
                text_to_classify = (raw_text or "").strip()

                if not text_to_classify:
                    doc.execution_log = TYPOLOGY.mark_value(doc.execution_log, identity)
                    flag_modified(doc, "execution_log")

                    continue

                valid_docs.append(doc)
                texts_buffer.append(text_to_classify)

            if texts_buffer:
                logger.info(f"🧠 Processing batch of {len(texts_buffer)} documents in the AI...")

                try:
                    results = engine.classify(texts_buffer, candidate_labels, batch_size=1)
                except Exception as e:
                    logger.error(f"❌ Error during pipeline inference: {e}")
                    uow.rollback()
                    break

                # Application of the results
                for doc, result in zip(valid_docs, results, strict=True):
                    failed = False
                    try:
                        best_label = result["labels"][0]
                        confidence_score = result["scores"][0]

                        if confidence_score > confidence_threshold:
                            t_id = typologies_map.get(best_label)

                            if t_id is not None:
                                doc.typology_id = t_id
                                logger.debug(
                                    f"Doc {doc.description_id} ➡️ {best_label} ({(confidence_score * 100):.1f}%)"
                                )
                            else:
                                logger.warning(
                                    f"Doc {doc.description_id}: Typology '{best_label}' not found in the database map."
                                )
                        else:
                            # An answer another producer wrote does not survive a refusal from this
                            # one. The stamp is the only gate now, so a document that came back to
                            # the classifier and was declined must not leave carrying a label the
                            # current producer does not sign — otherwise raising the floor would
                            # re-run the collection and change no label, which is the whole point of
                            # the identity.
                            if doc.typology_id is not None:
                                doc.typology_id = None
                            # And the refusal is recorded rather than inferred: the column is NULL
                            # both when the run declined and when it never reached the document, so
                            # the score it saw is the only thing that tells the two apart — and the
                            # one number a floor decision needs. The stamp cannot carry it (see
                            # ``AnomalyType.TYPOLOGY_LOW_CONFIDENCE``).
                            db.add(
                                ArchiveAIReviewQueue(
                                    anomaly_type=AnomalyType.TYPOLOGY_LOW_CONFIDENCE,
                                    status=ArchiveReviewStatus.NEEDS_REVIEW,
                                    context_payload={
                                        "description_id": doc.description_id,
                                        "title": doc.original_title,
                                    },
                                    llm_decision=best_label,
                                    llm_confidence=confidence_score,
                                    llm_reason=(
                                        f"A classificação de tipologia não atingiu o limiar "
                                        f"({confidence_threshold:.2f}); a descrição ficou sem tipologia."
                                    ),
                                )
                            )
                            logger.debug(f"Doc {doc.description_id} ignored (Low confidence)")

                        total_processed += 1

                    except Exception as e:
                        logger.error(f"❌ Error updating document {doc.description_id}: {e}")
                        # A failure must not be recorded as the current identity, or the document
                        # would look processed by this producer and never be retried.
                        failed = True
                    try:
                        doc.execution_log = (
                            TYPOLOGY.mark_failed(doc.execution_log)
                            if failed
                            else TYPOLOGY.mark_value(doc.execution_log, identity)
                        )
                        flag_modified(doc, "execution_log")
                    except Exception as e:
                        logger.critical(f"Critical failure trying to stamp the error on doc {doc.description_id}: {e}")

            try:
                uow.commit()
                logger.info(f"⏳ Partial progress: {total_processed} documents processed...")
            except Exception as e:
                uow.rollback()
                logger.error(f"💥 Failure committing to the database: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Unexpected error processing the batch: {e}")
            uow.rollback()
            break

    logger.success(f"✅ Typology Worker finished! Total processed in this run: {total_processed}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db)

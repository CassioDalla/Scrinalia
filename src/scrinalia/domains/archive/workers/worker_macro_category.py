from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.runner_config import MacroCategoryRunnerConfig
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.archive.domain.normalization import normalize_tag
from scrinalia.domains.archive.domain.vocabulary import is_subject_candidate, label_set_fingerprint
from scrinalia.domains.archive.engines.base import TypologyEngine
from scrinalia.domains.archive.engines.classification.registry import (
    EngineName,
    PresetName,
    describe_config,
    get_engine,
)
from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveReviewStatus,
    ArchiveTag,
)
from scrinalia.domains.archive.repository import TagRepository
from scrinalia.domains.archive.worker_stamp import (
    MACRO_CATEGORY,
    identity_stamp_conditions,
    producer_fingerprint,
)
from scrinalia.domains.archive.workers.cancellation import RunControl, checkpoint
from scrinalia.domains.archive.workers.run_budget import RunBudget


def resolved_threshold(config: MacroCategoryRunnerConfig | None, confidence_threshold: float | None) -> float:
    """The floor to link a drawer, resolved once for ``execute`` and the panel."""
    resolved = config or MacroCategoryRunnerConfig()
    return resolved.confidence_threshold if confidence_threshold is None else float(confidence_threshold)


def effective_options(confidence_threshold: float | None = None, **_options: Any) -> dict[str, Any]:
    """The floor a run really uses, through ``resolved_threshold`` (#120)."""
    return {"confidence_threshold": resolved_threshold(None, confidence_threshold)}


def producer_identity(
    *,
    engine_name: EngineName,
    preset: PresetName | None,
    categories_map: dict[str, Any],
    confidence_threshold: float,
    engine_kwargs: dict,
) -> str:
    """
    Identity of the subject classifier: the label set **and** the model that read it.

    Two changes have to re-queue an orphan tag by themselves, and they are different facts: a
    curator rewriting a label (the ``label_set_fingerprint`` precedent, which exists because the V3
    migration retired ``Instituição`` while its tags kept ``DONE``) and a model or threshold
    change. Both compose this one value, so the tag is pending with either.

    ``MacroCategoryRunnerConfig.review_threshold`` is deliberately absent: it is read nowhere in
    this worker, and hashing a value that changes no verdict would re-queue the collection for
    nothing.
    """
    config = describe_config(engine_name, preset, **engine_kwargs)
    return producer_fingerprint(
        axis="classification",
        engine_name=engine_name,
        preset=preset,
        engine_config=config,
        worker_options={
            "labels": label_set_fingerprint(categories_map),
            "confidence_threshold": confidence_threshold,
        },
    )


def pending_conditions(
    categories_map: dict[str, Any],
    producer: str,
    force: bool = False,
) -> list[ColumnElement[bool]]:
    """
    Predicate of the macro-category queue, shared by ``execute`` and the operations panel.

    The unit is the **tag**, not the document. A tag with a drawer already set is out of reach: the
    worker's queue is ``macro_category_id IS NULL``, so a curator's decision is never rewritten.
    Without an active drawer the worker cannot classify anything, so the predicate degrades to the
    orphan backlog — the panel then shows the real queue instead of a comforting zero.

    A tag stamped by another producer — another label set, engine or threshold — is pending again,
    and a tag the worker marked as failed stays out of the plain queue.
    """
    conditions: list[ColumnElement[bool]] = [ArchiveTag.macro_category_id.is_(None)]
    if not categories_map:
        return conditions
    conditions.extend(identity_stamp_conditions(ArchiveTag.execution_log, MACRO_CATEGORY, producer, force=force))
    return conditions


def count_pending(
    db: Session,
    force: bool = False,
    confidence_threshold: float | None = None,
    config: MacroCategoryRunnerConfig | None = None,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName | None = "cpu_local",
    **engine_kwargs: Any,
) -> int:
    """Tags the next classification run would read, under the identity it would write."""
    categories_map = TagRepository(db).get_active_macro_categories()
    threshold = resolved_threshold(config, confidence_threshold)
    identity = producer_identity(
        engine_name=engine_name,
        preset=preset,
        categories_map=categories_map,
        confidence_threshold=threshold,
        engine_kwargs=engine_kwargs,
    )
    stmt = select(func.count()).select_from(ArchiveTag).where(*pending_conditions(categories_map, identity, force))
    return int(db.scalar(stmt) or 0)


def execute(
    db: Session,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName = "cpu_local",
    db_batch_size: int = 64,
    config: MacroCategoryRunnerConfig | None = None,
    confidence_threshold: float | None = None,
    force: bool = False,
    limit: int | None = None,
    run_control: RunControl | None = None,
    **engine_kwargs,
) -> None:
    """
    Orchestrator of the Macro Category (subject axis) classification pipeline.

    Fetches, in batches, the orphan tags — those that still have no macro category —
    and classifies each tag name against the active macro categories registered by the
    curators. Unlike the document workers, the idempotency ledger lives on
    ``ArchiveTag.execution_log``, not on the document: the tag carries its own stamp.

    The confidence score is persisted even when it loses to the threshold, so a tag the
    model was unsure about is observable instead of invisible. Only a score above the
    threshold links the category; either way the tag is stamped, so it leaves the queue.

    Because a stamped-but-orphan tag is legitimately re-queueable (the curator may have
    registered the missing category later), the loop advances with a ``tag_id`` cursor and
    never revisits a row, keeping ``force=True`` finite.

    Args:
        db (Session): Database session.
        engine_name (EngineName, optional): Identifier of the AI engine registered in the
            system (e.g. "deberta_typology"). Default is "deberta_typology".
        preset (PresetName, optional): Pre-configuration that defines the engine's default
            hyperparameters. Default is "cpu_local".
        db_batch_size (int, optional): Number of tags fetched and saved per transaction.
            Default is 64.
        config (MacroCategoryRunnerConfig | None, optional): Business thresholds. When
            ``None``, the defaults of ``MacroCategoryRunnerConfig`` are used. The declared
            ``confidence_threshold`` wins over it, so a value measured by the bench can be tried
            without editing code.
        confidence_threshold (float | None, optional): The floor to link a drawer. ``None`` uses
            the one in ``config`` (0.55 by default).
        force (bool, optional): When ``True``, ignores the producer identity of orphan tags
            and reclassifies them. Already categorized tags are never touched. Default is
            ``False``.
        limit (int | None, optional): Cap on the tags this run touches, so a trial costs N tags
            instead of the collection. Not persisted. Default is ``None``.
        **engine_kwargs: Arbitrary arguments forwarded to the AI engine constructor,
            overriding the ``preset`` (e.g. ``device="cuda:0"``).

    Raises:
        Exception: If instantiating the processing engine fails (e.g. model not found).

    Returns:
        None. The process runs until the queue of orphan tags is emptied.
    """

    logger.info(f"🚀 Starting the Macro Category Worker (Engine: {engine_name} | Preset: {preset} | Force: {force})")

    confidence_threshold = resolved_threshold(config, confidence_threshold)

    repository = TagRepository(db)
    uow = UnitOfWork(db)

    try:
        logger.info("Loading Processing Engine...")
        engine: TypologyEngine = get_engine(engine_name=engine_name, preset=preset, **engine_kwargs)
    except Exception as e:
        logger.error(f"❌ Error loading the model: {e}")
        raise

    categories_map = repository.get_active_macro_categories()
    if not categories_map:
        logger.warning("⚠️ No macro category registered in the database. Aborting Classification.")
        return

    candidate_labels = list(categories_map.keys())

    # The stamp is the **identity of the producer**, not a status: the label set (rewriting one
    # label — or registering, retiring or renaming a drawer — changes it, and the V3 migration
    # retired ``Instituição`` while its tags kept ``DONE``, so the correction would never have
    # reached them) *and* the model with its threshold. Same trick as ``worker_embedding``,
    # applied to a catalog instead of a text.
    # The curated half of the NENHUMA class. The deterministic guard covers what has a
    # recognisable form; these are the judgements no rule reaches (``pessoas``, ``vista
    # aérea``, ``exemplo lugar``), where the model cannot abstain and answers confidently wrong.
    excluded_terms = repository.get_subject_exclusions()
    # The collection's own families — the toponyms and the person names — are rows, so the worker
    # hands them to the guard instead of the guard carrying the city's names in a regex.
    vocabulary = repository.collection_vocabulary()

    identity = producer_identity(
        engine_name=engine_name,
        preset=preset,
        categories_map=categories_map,
        confidence_threshold=confidence_threshold,
        engine_kwargs=engine_kwargs,
    )
    logger.info(f"📂 {len(candidate_labels)} macro categories loaded (identity {identity[:12]}).")
    if excluded_terms:
        logger.info(f"🚫 {len(excluded_terms)} curated subject exclusion(s) will be honoured.")

    where_cond: list[ColumnElement[bool]] = pending_conditions(categories_map, identity, force)

    query_count = select(func.count()).select_from(ArchiveTag).where(*where_cond)
    total_tags = db.scalar(query_count)

    if not total_tags:
        logger.info("✨ No pending tag found. Finishing.")
        return

    logger.info(f"🔍 Found {total_tags} tags to classify.")

    total_processed = 0
    last_tag_id = 0
    budget = RunBudget(limit)

    while True:
        checkpoint(run_control)
        try:
            query = (
                select(ArchiveTag)
                .where(*where_cond, ArchiveTag.tag_id > last_tag_id)
                .order_by(ArchiveTag.tag_id)
                .limit(budget.batch_size(db_batch_size))
            )
            batch_tags = db.scalars(query).all()

            if not batch_tags:
                break

            last_tag_id = batch_tags[-1].tag_id
            budget.spend(len(batch_tags))

            logger.info(f"🧠 Processing batch of {len(batch_tags)} tags in the AI...")

            # The deterministic guard runs first: a bare year, a placeholder or a street is
            # not a subject and never reaches the model. Measured, this is ~1.600 documents
            # that today receive a confident wrong answer (``1924`` -> "Mobilidade" with
            # 0.73), and a rule cannot hallucinate the way an abstention threshold can.
            classifiable = [
                tag
                for tag in batch_tags
                if is_subject_candidate(tag.name, vocabulary) and normalize_tag(tag.name) not in excluded_terms
            ]
            skipped = len(batch_tags) - len(classifiable)

            try:
                results = (
                    engine.classify([tag.name for tag in classifiable], candidate_labels, batch_size=1)
                    if classifiable
                    else []
                )
            except Exception as e:
                logger.error(f"❌ Error during pipeline inference: {e}")
                uow.rollback()
                break

            if skipped:
                logger.debug(f"⏭️ {skipped} tag(s) skipped as non-subjects (date, placeholder or street).")

            # Stamped with the current producer identity: the guard is a verdict, not a
            # failure, so a re-run must not revisit them unless the vocabulary or the model
            # changes.
            for tag in batch_tags:
                if tag in classifiable:
                    continue
                tag.macro_category_id = None
                tag.ai_confidence_score = None
                tag.execution_log = MACRO_CATEGORY.mark_value(tag.execution_log, identity)
                flag_modified(tag, "execution_log")
                total_processed += 1

            for tag, result in zip(classifiable, results, strict=True):
                failed = False
                try:
                    best_label = result["labels"][0]
                    confidence_score = float(result["scores"][0])

                    # Always persisted: it is the observability of a near miss.
                    tag.ai_confidence_score = confidence_score

                    if confidence_score > confidence_threshold:
                        category_id = categories_map.get(best_label)

                        if category_id is not None:
                            tag.macro_category_id = category_id
                            logger.debug(f"Tag {tag.tag_id} '{tag.name}' ➡️ {best_label} ({confidence_score:.1%})")
                        else:
                            logger.warning(f"Tag {tag.tag_id}: category '{best_label}' not found in the database map.")
                    else:
                        # Not linked, and it must not vanish: the curator gets a decision to
                        # make. Below the floor the model is guessing (measured: a wrong
                        # answer averages 0.455), and a silent orphan reads as "nothing to
                        # see here" — the opposite of the truth.
                        logger.debug(f"Tag {tag.tag_id} '{tag.name}' sent to review ({confidence_score:.1%})")
                        db.add(
                            ArchiveAIReviewQueue(
                                anomaly_type=AnomalyType.SUBJECT_LOW_CONFIDENCE,
                                status=ArchiveReviewStatus.NEEDS_REVIEW,
                                context_payload={"tag_id": tag.tag_id, "tag_name": tag.name},
                                llm_decision=best_label,
                                llm_confidence=confidence_score,
                                llm_reason=(
                                    f"A classificação de assunto não atingiu o limiar "
                                    f"({confidence_threshold:.2f}); a tag ficou sem categoria."
                                ),
                            )
                        )

                    total_processed += 1

                except Exception as e:
                    logger.error(f"❌ Error updating tag {tag.tag_id}: {e}")
                    # An error must NOT be recorded as the current label set, otherwise the
                    # failure would look processed and the tag would never be retried.
                    failed = True

                try:
                    tag.execution_log = (
                        MACRO_CATEGORY.mark_failed(tag.execution_log)
                        if failed
                        else MACRO_CATEGORY.mark_value(tag.execution_log, identity)
                    )
                    flag_modified(tag, "execution_log")
                except Exception as e:
                    logger.critical(f"Critical failure trying to stamp the error on tag {tag.tag_id}: {e}")

            try:
                uow.commit()
                logger.info(f"⏳ Partial progress: {total_processed} tags processed...")
            except Exception as e:
                uow.rollback()
                logger.error(f"💥 Failure committing to the database: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Unexpected error processing the batch: {e}")
            uow.rollback()
            break

    logger.success(f"✅ Macro Category Worker finished! Total processed in this run: {total_processed}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db)

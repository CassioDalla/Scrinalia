from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.core.runner_config import MacroCategoryRunnerConfig
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.archive.domain.normalization import normalize_tag
from memoria_curitibana.domains.archive.domain.vocabulary import is_subject_candidate, label_set_fingerprint
from memoria_curitibana.domains.archive.engines.base import TypologyEngine
from memoria_curitibana.domains.archive.engines.classification.registry import EngineName, PresetName, get_engine
from memoria_curitibana.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveReviewStatus,
    ArchiveTag,
)
from memoria_curitibana.domains.archive.repository import TagRepository
from memoria_curitibana.domains.archive.worker_stamp import MACRO_CATEGORY


def execute(
    db: Session,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName = "cpu_local",
    db_batch_size: int = 64,
    config: MacroCategoryRunnerConfig | None = None,
    force: bool = False,
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
            ``None``, the defaults of ``MacroCategoryRunnerConfig`` are used.
        force (bool, optional): When ``True``, ignores the idempotency stamp of orphan tags
            and reclassifies them. Already categorized tags are never touched. Default is
            ``False``.
        **engine_kwargs: Arbitrary arguments forwarded to the AI engine constructor,
            overriding the ``preset`` (e.g. ``device="cuda:0"``).

    Raises:
        Exception: If instantiating the processing engine fails (e.g. model not found).

    Returns:
        None. The process runs until the queue of orphan tags is emptied.
    """

    logger.info(f"🚀 Starting the Macro Category Worker (Engine: {engine_name} | Preset: {preset} | Force: {force})")

    config = config or MacroCategoryRunnerConfig()

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

    # The stamp is the identity of the label set, not a status. Rewriting one label — or
    # registering, retiring or renaming a drawer — changes this hash, which is what puts the
    # already-classified tags back in the queue. A status stamp could not do that, and the
    # failure is not hypothetical: the V3 migration retired ``Instituição`` while its tags
    # kept ``worker_macro_category_v1: DONE``, so the correction would never have reached
    # them. Same trick as ``worker_embedding``, applied to a catalog instead of a text.
    # The curated half of the NENHUMA class. The deterministic guard covers what has a
    # recognisable form; these are the judgements no rule reaches (``pessoas``, ``vista
    # aérea``, ``capanema``), where the model cannot abstain and answers confidently wrong.
    excluded_terms = repository.get_subject_exclusions()

    label_fingerprint = label_set_fingerprint(categories_map)
    logger.info(f"📂 {len(candidate_labels)} macro categories loaded (labels {label_fingerprint[:12]}).")
    if excluded_terms:
        logger.info(f"🚫 {len(excluded_terms)} curated subject exclusion(s) will be honoured.")

    where_cond: list[ColumnElement[bool]] = [ArchiveTag.macro_category_id.is_(None)]

    if not force:
        # A tag whose stamp already carries this label set left the queue, even if it stayed
        # orphan because the best score was below the threshold. A stamp with a *different*
        # value is pending: the vocabulary changed under it.
        where_cond.append(
            or_(
                ArchiveTag.execution_log.is_(None),
                ~ArchiveTag.execution_log.has_key(MACRO_CATEGORY.key),
                func.coalesce(ArchiveTag.execution_log[MACRO_CATEGORY.key].astext, "") != label_fingerprint,
            )
        )

    query_count = select(func.count()).select_from(ArchiveTag).where(*where_cond)
    total_tags = db.scalar(query_count)

    if not total_tags:
        logger.info("✨ No pending tag found. Finishing.")
        return

    logger.info(f"🔍 Found {total_tags} tags to classify.")

    total_processed = 0
    last_tag_id = 0

    while True:
        try:
            query = (
                select(ArchiveTag)
                .where(*where_cond, ArchiveTag.tag_id > last_tag_id)
                .order_by(ArchiveTag.tag_id)
                .limit(db_batch_size)
            )
            batch_tags = db.scalars(query).all()

            if not batch_tags:
                break

            last_tag_id = batch_tags[-1].tag_id

            logger.info(f"🧠 Processing batch of {len(batch_tags)} tags in the AI...")

            # The deterministic guard runs first: a bare year, a placeholder or a street is
            # not a subject and never reaches the model. Measured, this is ~1.600 documents
            # that today receive a confident wrong answer (``1924`` -> "Mobilidade" with
            # 0.73), and a rule cannot hallucinate the way an abstention threshold can.
            classifiable = [
                tag
                for tag in batch_tags
                if is_subject_candidate(tag.name) and normalize_tag(tag.name) not in excluded_terms
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

            # Stamped as processed with the current label set: the guard is a verdict, not a
            # failure, so a re-run must not revisit them unless the vocabulary changes.
            for tag in batch_tags:
                if tag in classifiable:
                    continue
                tag.macro_category_id = None
                tag.ai_confidence_score = None
                tag.execution_log = MACRO_CATEGORY.mark_value(tag.execution_log, label_fingerprint)
                flag_modified(tag, "execution_log")
                total_processed += 1

            for tag, result in zip(classifiable, results, strict=True):
                stamp_value = label_fingerprint
                try:
                    best_label = result["labels"][0]
                    confidence_score = float(result["scores"][0])

                    # Always persisted: it is the observability of a near miss.
                    tag.ai_confidence_score = confidence_score

                    if confidence_score > config.confidence_threshold:
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
                                    f"({config.confidence_threshold:.2f}); a tag ficou sem gaveta."
                                ),
                            )
                        )

                    total_processed += 1

                except Exception as e:
                    logger.error(f"❌ Error updating tag {tag.tag_id}: {e}")
                    # An error must NOT be recorded as the current label set, otherwise the
                    # failure would look processed and the tag would never be retried.
                    stamp_value = "ERROR"

                try:
                    tag.execution_log = MACRO_CATEGORY.mark_value(tag.execution_log, stamp_value)
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

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql.elements import ColumnElement

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.core.runner_config import TypologyRunnerConfig
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.archive.engines.base import TypologyEngine
from memoria_curitibana.domains.archive.engines.classification.registry import EngineName, PresetName, get_engine
from memoria_curitibana.domains.archive.models import ArchiveDocument
from memoria_curitibana.domains.archive.repository import TypologyRepository
from memoria_curitibana.domains.archive.repository.governance import ai_writable_documents
from memoria_curitibana.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    composed_text_sql,
)
from memoria_curitibana.domains.archive.worker_stamp import TYPOLOGY


def pending_conditions(columns_to_classify: list[str]) -> list[ColumnElement[bool]]:
    """
    Predicate of the typology queue, shared by ``execute`` and the operations panel.

    A document that already carries a typology is out, and so is one a human approved: the AI must
    not reclassify a decision someone made.
    """
    filters_columns = [getattr(ArchiveDocument, col).is_not(None) for col in columns_to_classify]
    return [
        ArchiveDocument.typology_id.is_(None),
        ai_writable_documents(),
        or_(*filters_columns),
        or_(
            ArchiveDocument.execution_log.is_(None),
            ~ArchiveDocument.execution_log.has_key(TYPOLOGY.key),
        ),
    ]


def count_pending(
    db: Session,
    columns_to_classify: list[str] | None = None,
    config: TypologyRunnerConfig | None = None,
    **options,
) -> int:
    """Documents the next typology run would classify."""
    resolved = config or TypologyRunnerConfig()
    columns = columns_to_classify or list(resolved.columns_to_classify)
    stmt = select(func.count()).select_from(ArchiveDocument).where(*pending_conditions(columns))
    return int(db.scalar(stmt) or 0)


def execute(
    db: Session,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName = "cpu_local",
    db_batch_size: int = 64,
    columns_to_classify: list[str] | None = None,
    config: TypologyRunnerConfig | None = None,
    **engine_kwargs,
) -> None:
    """
    Orchestrator of the Document Typology Classification pipeline.

    Continuously fetches, in batches, the documents in the database that have not
    yet been processed by this routine (checking the JSON column `execution_log`).
    Dynamically concatenates the requested columns to form the context and uses
    an Artificial Intelligence engine injected via the Registry to classify
    the document into one of the active typologies in the system.

    If the inference confidence (confidence score) is above 40%, it links the
    `typology_id` to the document. Regardless of the classification success,
    the document is stamped as "DONE" so it does not enter a loop. The processing
    is shielded with memory protection (expunge_all) after each completed transaction.

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
        **engine_kwargs: Arbitrary arguments that will be forwarded directly to
            the AI engine constructor, overriding the `preset` configurations
            (e.g. `device="cuda:0"`, `max_length=256`).

    Raises:
        Exception: If there is a catastrophic failure instantiating the processing engine
            (e.g. model not found, machine out of memory).

    Returns:
        None. The process runs until the database queue is emptied.
    """

    logger.info(f"🚀 Starting the Typology Classifier Worker (Engine: {engine_name} | Preset: {preset})")

    config = config or TypologyRunnerConfig()
    columns_to_classify = columns_to_classify or list(config.columns_to_classify)

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

    candidate_labels = list(typologies_map.keys())
    logger.info(f"📂 {len(candidate_labels)} typologies loaded.")

    # Fetches the ArchiveDocument class attributes at runtime
    where_cond = pending_conditions(columns_to_classify)

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

    while True:
        try:
            query = (
                select(ArchiveDocument, text_expression.label("effective_text")).where(*where_cond).limit(db_batch_size)
            )

            batch_rows = db.execute(query).all()

            if not batch_rows:
                break

            texts_buffer = []
            valid_docs = []

            # Text preparation (already composed by PostgreSQL)
            for doc, raw_text in batch_rows:
                text_to_classify = (raw_text or "").strip()

                if not text_to_classify:
                    doc.execution_log = TYPOLOGY.mark(doc.execution_log)
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
                    stamp_status = "DONE"
                    try:
                        best_label = result["labels"][0]
                        confidence_score = result["scores"][0]

                        if confidence_score > config.confidence_threshold:
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
                            logger.debug(f"Doc {doc.description_id} ignored (Low confidence)")

                        total_processed += 1

                    except Exception as e:
                        logger.error(f"❌ Error updating document {doc.description_id}: {e}")
                        stamp_status = "ERROR"
                    try:
                        doc.execution_log = TYPOLOGY.mark(doc.execution_log, status=stamp_status)
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

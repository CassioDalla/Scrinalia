from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.logger import logger
from domains.archive.engines.base import TypologyEngine
from domains.archive.engines.classification.registry import EngineName, PresetName, get_engine
from domains.archive.models import ArchiveDocument
from domains.archive.repository import TypologyRepository


def execute(
    db: Session,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName = "cpu_local",
    db_batch_size: int = 64,
    columns_to_classify: list[str] | None = None,
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

    columns_to_classify = columns_to_classify or ["original_title"]

    repository = TypologyRepository(db)

    try:
        logger.info("Loading Processing Engine...")
        engine: TypologyEngine = get_engine(engine_name=engine_name, preset=preset, **engine_kwargs)
    except Exception as e:
        logger.error(f"❌ Error loading the model: {e}")
        raise

    typologies_map = repository.get_active_typologies()
    print(typologies_map)
    if not typologies_map:
        logger.warning("⚠️ No typology registered in the database. Aborting Classification.")
        return

    candidate_labels = list(typologies_map.keys())
    logger.info(f"📂 {len(candidate_labels)} typologies loaded.")

    # Fetches the ArchiveDocument class attributes at runtime
    filters_columns = [getattr(ArchiveDocument, col).is_not(None) for col in columns_to_classify]
    where_cond = [
        ArchiveDocument.typology_id.is_(None),
        or_(*filters_columns),
        or_(
            ArchiveDocument.execution_log.is_(None),
            ~ArchiveDocument.execution_log.has_key("worker_typology_classifier_v1"),
        ),
    ]

    query_count = select(func.count()).select_from(ArchiveDocument).where(*where_cond)
    total_documents = db.scalar(query_count)

    if not total_documents:
        logger.info("✨ No pending document found. Finishing.")
        return

    logger.info(f"🔍 Found {total_documents} documents to classify.")

    total_processed = 0

    while True:
        try:
            query = select(ArchiveDocument).where(*where_cond).limit(db_batch_size)

            batch_docs = db.scalars(query).all()

            if not batch_docs:
                break

            texts_buffer = []
            valid_docs = []

            # Text preparation
            for doc in batch_docs:
                text_parts = []

                for col in columns_to_classify:
                    value = getattr(doc, col, None)
                    if value and str(value).strip():
                        text_parts.append(str(value).strip())

                text_to_classify = ". ".join(text_parts)

                if not text_to_classify:
                    current_log = dict(doc.execution_log) if doc.execution_log else {}
                    current_log["worker_typology_classifier_v1"] = "DONE"
                    doc.execution_log = current_log
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
                    db.rollback()
                    break

                # Application of the results
                for doc, result in zip(valid_docs, results):  # noqa: B905
                    stamp_status = "DONE"
                    try:
                        best_label = result["labels"][0]
                        confidence_score = result["scores"][0]

                        if confidence_score > 0.40:
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
                        current_log = dict(doc.execution_log) if doc.execution_log else {}
                        current_log["worker_typology_classifier_v1"] = stamp_status
                        doc.execution_log = current_log
                        flag_modified(doc, "execution_log")
                    except Exception as e:
                        logger.critical(f"Critical failure trying to stamp the error on doc {doc.description_id}: {e}")

            try:
                db.commit()
                logger.info(f"⏳ Partial progress: {total_processed} documents processed...")
            except Exception as e:
                db.rollback()
                logger.error(f"💥 Failure committing to the database: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Unexpected error processing the batch: {e}")
            db.rollback()
            break

    logger.success(f"✅ Typology Worker finished! Total processed in this run: {total_processed}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db)

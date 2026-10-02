import re
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.logger import logger
from domains.archive.engines.base import EntityExtractionEngine
from domains.archive.engines.NER.registry import EngineName as ExtractEngineName
from domains.archive.engines.NER.registry import PresetName, get_engine
from domains.archive.models import ArchiveDocument, ArchiveReviewStatus, DomainStopwords, StopwordsScope
from domains.archive.repository import EntityRepository


def load_entity_blacklist(db_session: Session) -> set[str]:
    """Loads all entity stopwords into a Python SET (O(1) lookup)."""
    result = (
        db_session.query(DomainStopwords.word)
        .filter(DomainStopwords.word_scope.in_([StopwordsScope.ENTITY, StopwordsScope.ALL]))
        .all()
    )
    return {row[0].lower() for row in result}


def _clean_raw_text(text: str) -> str:
    """Helper to clean basic noise before sending it to the AI."""

    if not text:
        return ""

    # 1. Removes URLs (http, https, www)
    text_no_urls = re.sub(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "", text)
    text_no_urls = re.sub(r"www\.\S+", "", text_no_urls)

    # 2. Removes e-mails
    text_no_urls = re.sub(r"[\w\.-]+@[\w\.-]+", "", text_no_urls)

    return text_no_urls.strip()


def execute(
    db: Session,
    engine_name: ExtractEngineName = "spacy_ner",
    preset: PresetName = "gpu",
    db_batch_size: int = 64,
    columns_to_extract: list[str] | None = None,
    **engine_kwargs: Any,
) -> None:
    """
    Main orchestrator of the Named Entity Recognition (NER) pipeline.

    Implements an asynchronous batch processing pattern
    with memory protection. The worker fetches documents from the database that do not
    yet have the 'worker_ner_v1' key in the JSON column `execution_log`.

    For each batch, the orchestrator:
    1. Concatenates and sanitizes the configured text columns.
    2. Sends the texts to the injected AI engine (Strategy pattern via Registry)
       together with institutional rules loaded dynamically.
    3. Persists the found entities (UPSERT) and creates the N:N relationships.
    4. Applies a universal stamp ("DONE" or "ERROR") on the document to guarantee
       that the queue advances, preventing infinite loops on inference failure.

    The database session is expunged (expunge_all) after each completed transaction to
    avoid memory leaks in long-running executions.

    Args:
        db (Session): Active SQLAlchemy session injected by the caller.
        engine_name (ExtractEngineName, optional): Registration key of the NLP
            processing engine to be instantiated. Default is "spacy_ner".
        preset (PresetName, optional): Predefined hardware/model configuration
            for the engine (e.g. "gpu", "cpu_local"). Default is "gpu".
        db_batch_size (int, optional): Limit of documents fetched and committed
            per transaction in the database. Default is 64.
        columns_to_extract (list[str] | None, optional): List of attributes of the model
            `ArchiveDocument` that will form the context analyzed by the AI. If `None`,
            it uses `["original_title", "admin_bio_history", "provenance", "scope_content"]`.
        **engine_kwargs (Any): Extra keyword arguments forwarded directly to the
            AI engine constructor to override preset configurations.

    Raises:
        Exception: If there is a critical failure loading the NLP engine or the
            configured hardware dependencies.

    Returns:
        None. The pipeline processes batches continuously until the database queue
        is completely empty.

    """
    logger.info(f"🚀 Starting the NER Worker (Engine: {engine_name} | Preset: {preset})")

    columns_to_extract = columns_to_extract or ["original_title", "admin_bio_history", "provenance", "scope_content"]
    repository = EntityRepository(db)

    try:
        logger.info("Loading Extraction Engine and dynamic rules...")
        dynamic_rules = repository.get_ner_synonyms_rules()
        # The engine must be able to receive these rules in the constructor or via a setup() method
        engine: EntityExtractionEngine = get_engine(
            engine_name=engine_name, preset=preset, custom_rules=dynamic_rules, **engine_kwargs
        )

    except Exception as e:
        logger.error(f"❌ Error instantiating the NER engine: {e}")
        raise

    # 1. Filters (We look for docs that do NOT yet have the NER stamp).
    # HUMAN_APPROVED documents are shielded: the AI must not overwrite human curation.
    filters_columns = [getattr(ArchiveDocument, col).is_not(None) for col in columns_to_extract]
    where_cond = [
        ArchiveDocument.review_status != ArchiveReviewStatus.HUMAN_APPROVED,
        or_(*filters_columns),
        or_(
            ArchiveDocument.execution_log.is_(None),
            ~ArchiveDocument.execution_log.has_key("worker_ner_v1"),
        ),
    ]

    # Pre-Query for the logs
    query_count = select(func.count()).select_from(ArchiveDocument).where(*where_cond)
    total_documents = db.scalar(query_count)

    if not total_documents:
        logger.info("✨ No pending documents for entity extraction.")
        return

    logger.info(f"🔍 Found {total_documents} documents to process.")

    blacklist = load_entity_blacklist(db)
    logger.info(f"🛡️ Loaded {len(blacklist)} words into the NER blacklist.")

    processed_docs_count = 0
    while True:
        try:
            query = select(ArchiveDocument).where(*where_cond).limit(db_batch_size)
            batch_docs = db.scalars(query).all()

            if not batch_docs:
                break

            texts_buffer = []
            valid_docs = []

            # 2. Preparation and Cleaning of the texts
            for doc in batch_docs:
                text_parts = []

                for col in columns_to_extract:
                    value = getattr(doc, col, None)
                    if value and str(value).strip():
                        text_parts.append(str(value).strip())

                text_contextualized = ". ".join(text_parts)
                text_contextualized = _clean_raw_text(text_contextualized)

                if not text_contextualized:
                    # Stamps empty docs so they do not enter a loop
                    current_log = dict(doc.execution_log) if doc.execution_log else {}
                    current_log["worker_ner_v1"] = "DONE"
                    doc.execution_log = current_log
                    flag_modified(doc, "execution_log")
                    continue

                valid_docs.append(doc)
                texts_buffer.append(text_contextualized)

            batch_links_buffer = []
            if texts_buffer:
                logger.info(f"🧠 Extracting entities from {len(texts_buffer)} documents...")

                # 3. Batch inference isolated in the try/except
                try:
                    # The engine must receive a list of texts and return a list of results
                    # (where each result is a list of ArchiveEntityDTO)
                    ner_results = engine.extract(texts_buffer)
                except Exception as e:
                    logger.error(f"❌ Failure in the AI processing: {e}")
                    db.rollback()
                    break

                # 4. Application of the Results and Persistence in the Database
                for doc, dtos_entities in zip(valid_docs, ner_results, strict=True):
                    stamp_status = "DONE"
                    doc = cast(ArchiveDocument, doc)
                    try:
                        # If the AI found entities, we process the links
                        if dtos_entities:
                            filtered_dtos = [ent for ent in dtos_entities if ent.name.strip().lower() not in blacklist]

                            if filtered_dtos:
                                try:
                                    with db.begin_nested():
                                        entity_ids = repository.get_or_create_entities(filtered_dtos)

                                        for e_id in entity_ids:
                                            batch_links_buffer.append(
                                                {"description_id": doc.description_id, "entity_id": e_id}
                                            )

                                        logger.debug(
                                            f"Doc {doc.description_id} ➡️ {len(entity_ids)} entities ready for linking."
                                        )
                                except Exception as e_nested:
                                    logger.error(f"❌ Transactional error in doc {doc.description_id}: {e_nested}")
                                    stamp_status = "ERROR"
                            else:
                                logger.debug(f"Doc {doc.description_id} ➡️ All entities blocked by the Blacklist.")
                        else:
                            logger.debug(f"Doc {doc.description_id} ➡️ No entity found.")

                        processed_docs_count += 1

                    except Exception as e:
                        logger.error(f"❌ Structural error saving entities for doc {doc.description_id}: {e}")
                        stamp_status = "ERROR"

                    # 5. The Universal Protection Stamp
                    try:
                        current_log = dict(doc.execution_log) if doc.execution_log else {}
                        current_log["worker_ner_v1"] = stamp_status
                        doc.execution_log = current_log
                        flag_modified(doc, "execution_log")
                    except Exception as e:
                        logger.critical(f"Critical failure stamping the error on doc {doc.description_id}: {e}")

            # 6. Batch Commit and Memory Cleanup
            try:
                if batch_links_buffer:
                    repository.bulk_link_entities(batch_links_buffer)

                db.commit()
                logger.info(f"⏳ Partial progress: {processed_docs_count} documents enriched...")
            except Exception as e:
                db.rollback()
                logger.error(f"💥 Failure committing to the database: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Unexpected error in the main loop of the NER Worker: {e}")
            db.rollback()
            break

    logger.success(f"✅ NER Worker finished! Total processed in this run: {processed_docs_count}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db, db_batch_size=100)

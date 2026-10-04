from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.archive.engines.base import EmbeddingEngine
from memoria_curitibana.domains.archive.engines.embeddings.registry import EngineName, PresetName, get_engine
from memoria_curitibana.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from memoria_curitibana.domains.archive.worker_stamp import EMBEDDING

# Columns whose content is embedded. The hash covers both title spellings, so replacing
# the original title with a human ``final_title`` also re-queues the document.
EMBEDDING_COLUMNS: tuple[str, ...] = (
    "original_title",
    "final_title",
    "scope_content",
    "admin_bio_history",
    "provenance",
)


def text_hash_expression() -> ColumnElement[str]:
    """
    MD5 of the embedded content, computed by PostgreSQL.

    The worker stores this hash as its idempotency stamp, which turns the pending query
    into a pure SQL comparison: a document is pending when its stored hash differs from
    the current one. Computing the hash in SQL keeps the read side and the write side
    using exactly the same definition.
    """
    parts = [func.nullif(func.btrim(getattr(ArchiveDocument, column)), "") for column in EMBEDDING_COLUMNS]
    return func.md5(func.concat_ws("\n", *parts))


def build_embedding_text(doc: ArchiveDocument) -> str:
    """Composes the text handed to the embedding model: title first, then the body."""
    parts: list[str] = []

    title = doc.final_title or doc.original_title
    if title and title.strip():
        parts.append(title.strip())

    for column in ("scope_content", "admin_bio_history", "provenance"):
        value = getattr(doc, column)
        if value and str(value).strip():
            parts.append(str(value).strip())

    return "\n".join(parts)


def execute(
    db: Session,
    engine_name: EngineName = "sentence_transformer",
    preset: PresetName = "multilingual_minilm",
    db_batch_size: int = 64,
    force: bool = False,
    **engine_kwargs,
) -> None:
    """
    Orchestrator of the semantic embedding pipeline.

    Fills ``ArchiveDocument.embedding`` with the vector of the document text, so the
    collection can be searched by concept instead of by lexeme. The stamp written in
    ``execution_log`` is the MD5 of the embedded text, not a status: a document whose
    text changed is pending again, even when a human edited it.

    ⚠️ GOVERNANCE EXCEPTION: this is the only AI worker that does **not** use
    ``ai_writable_documents()``. The embedding is a derived index of the text, not
    archival content, so a ``HUMAN_APPROVED`` document whose text changed must be
    re-embedded or semantic search would serve a stale vector. The worker writes only
    the ``embedding`` column and its own stamp; it never touches a reviewed field.

    Documents in ``REJECTED`` are skipped: they are not served, so there is nothing to
    index. Documents with no text at all are stamped without a vector so they leave the
    queue instead of being retried forever.

    Args:
        db (Session): Database session.
        engine_name (EngineName, optional): Identifier of the embedding engine registered
            in the system. Default is "sentence_transformer".
        preset (PresetName, optional): Pre-configuration with the model and its device.
            Default is "multilingual_minilm".
        db_batch_size (int, optional): Number of documents embedded and saved per
            transaction. Default is 64.
        force (bool, optional): When ``True``, ignores the content stamp and re-embeds
            every non-rejected document once. Default is ``False``.
        **engine_kwargs: Arbitrary arguments forwarded to the engine constructor,
            overriding the ``preset`` (e.g. ``device="cuda:0"``).

    Raises:
        Exception: If instantiating the embedding engine fails (e.g. model not found).

    Returns:
        None. The process runs until the queue of pending documents is emptied.
    """

    logger.info(f"🚀 Starting the Embedding Worker (Engine: {engine_name} | Preset: {preset} | Force: {force})")

    uow = UnitOfWork(db)

    try:
        logger.info("Loading Processing Engine...")
        engine: EmbeddingEngine = get_engine(engine_name=engine_name, preset=preset, **engine_kwargs)
    except Exception as e:
        logger.error(f"❌ Error loading the model: {e}")
        raise

    text_hash = text_hash_expression()

    where_cond: list[ColumnElement[bool]] = [
        ArchiveDocument.review_status != ArchiveReviewStatus.REJECTED,
    ]

    if not force:
        # NULL (no stamp yet) is DISTINCT FROM the hash, so the condition covers both
        # the first run and every later text change in a single predicate.
        where_cond.append(ArchiveDocument.execution_log[EMBEDDING.key].astext.is_distinct_from(text_hash))

    total_pending = db.scalar(select(func.count()).select_from(ArchiveDocument).where(*where_cond))

    if not total_pending:
        logger.info("✨ No pending document found. Finishing.")
        return

    logger.info(f"🔍 Found {total_pending} documents to embed.")

    total_processed = 0
    last_id = ""

    while True:
        try:
            query = (
                select(ArchiveDocument, text_hash.label("text_hash"))
                .where(*where_cond, ArchiveDocument.description_id > last_id)
                .order_by(ArchiveDocument.description_id)
                .limit(db_batch_size)
            )
            rows = db.execute(query).all()

            if not rows:
                break

            last_id = rows[-1][0].description_id

            texts: list[str] = []
            pending_docs: list[tuple[ArchiveDocument, str]] = []

            for doc, current_hash in rows:
                text = build_embedding_text(doc)

                if not text:
                    # Nothing to embed: stamp it so it leaves the queue for good.
                    doc.execution_log = EMBEDDING.mark_value(doc.execution_log, current_hash)
                    flag_modified(doc, "execution_log")
                    continue

                texts.append(text)
                pending_docs.append((doc, current_hash))

            if texts:
                logger.info(f"🧠 Embedding a batch of {len(texts)} documents...")

                try:
                    vectors = engine.embed(texts)
                except Exception as e:
                    logger.error(f"❌ Error during embedding inference: {e}")
                    uow.rollback()
                    break

                for (doc, current_hash), vector in zip(pending_docs, vectors, strict=True):
                    try:
                        doc.embedding = vector
                        doc.execution_log = EMBEDDING.mark_value(doc.execution_log, current_hash)
                        total_processed += 1
                    except Exception as e:
                        logger.error(f"❌ Error updating document {doc.description_id}: {e}")
                        doc.execution_log = EMBEDDING.mark(doc.execution_log, status="ERROR")

                    flag_modified(doc, "execution_log")

            try:
                uow.commit()
                logger.info(f"⏳ Partial progress: {total_processed} documents embedded...")
            except Exception as e:
                uow.rollback()
                logger.error(f"💥 Failure committing to the database: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Unexpected error processing the batch: {e}")
            uow.rollback()
            break

    logger.success(f"✅ Embedding Worker finished! Total processed in this run: {total_processed}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db)

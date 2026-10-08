from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.archive.engines.LLMs.registry import EngineName, PresetName, get_engine
from scrinalia.domains.archive.models import ArchiveReviewStatus
from scrinalia.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from scrinalia.domains.archive.repository import EntityRepository


def count_judged(db: Session, **options: Any) -> int:
    """
    Pairs already decided by the judge, read from the review queue.

    This is not the *pending* queue, and it is deliberately not the live trigram scan: that scan
    compares every tag with every entity and measured 53 s on the real collection. Every decision —
    auto-resolved or sent to a human — leaves a row in ``archive_ai_review_queue``, so the count is
    an indexed read of what has been judged.
    """
    stmt = (
        select(func.count())
        .select_from(ArchiveAIReviewQueue)
        .where(ArchiveAIReviewQueue.anomaly_type == AnomalyType.CROSS_DOMAIN_COLLISION)
    )
    return int(db.scalar(stmt) or 0)


def execute(
    db: Session,
    similarity_threshold: float = 0.90,
    auto_resolve_threshold: float = 0.85,
    engine_name: EngineName = "ollama_judge",
    preset: PresetName = "gemma_4b_local",
) -> None:
    """
    Worker that acts as a Judge (Human-in-the-Loop) to resolve semantic collisions.
    Uses a structured LLM to define whether an ambiguous term should belong
    to the Subject (Tags) taxonomy or to Named Entities (NER).
    """
    logger.info(f"⚖️ Starting the Tag/Entity Worker (Engine: {engine_name} | Preset: {preset})")

    # 1. Instantiates the repository and the AI Engine using the Registry
    ent_repo = EntityRepository(db)
    uow = UnitOfWork(db)

    try:
        llm_engine = get_engine(engine_name=engine_name, preset=preset)
    except Exception as e:
        logger.critical(f"❌ Failure loading the judging engine: {e}")
        return

    # 2. Trigram Scan: Looks for collisions in the archive (PostgreSQL)
    logger.info("Starting conflict scan")
    raw_conflicts = ent_repo.get_cross_domain_conflicts(similarity_threshold)

    if not raw_conflicts:
        logger.info("✨ Scan completed. No pending semantic conflict found.")
        return

    logger.info(f"✨ Scan completed. Found: {len(raw_conflicts)} conflicts")

    auto_successes = 0
    sent_to_review = 0
    failures = 0

    for row in raw_conflicts:
        # Unique digital signature to identify this conflict in the queue JSONB
        identifier_payload = {"tag_id": row.tag_id, "entity_id": row.entity_id}

        # 3. Protection against Rework: Checks whether this pair is already in the queue
        already_processed = db.scalar(
            select(ArchiveAIReviewQueue.id).where(
                ArchiveAIReviewQueue.anomaly_type == AnomalyType.CROSS_DOMAIN_COLLISION,
                ArchiveAIReviewQueue.context_payload.contains(identifier_payload),
            )
        )

        if already_processed:
            continue

        logger.info(
            f"🧠 Consulting the AI for the ambiguity: '{row.tag_name}' (Tag) vs '{row.entity_name}' ({row.entity_type})..."
        )

        try:
            # 4. Triggers the AI (Guarantees a structured return via Pydantic/JSON)
            decision = llm_engine.decide_conflict(
                tag_name=row.tag_name, entity_name=row.entity_name, entity_type=row.entity_type
            )

            final_status = ArchiveReviewStatus.NEEDS_REVIEW

            # 5. Direct Action (High Confidence): The Repository resolves the collision atomically
            if decision.confidence >= auto_resolve_threshold:
                # We use a savepoint to protect the current iteration against structural failures (e.g. Constraints)
                try:
                    with db.begin_nested():
                        ent_repo.resolve_cross_domain_conflict(
                            winner=decision.winner, tag_id=row.tag_id, entity_id=row.entity_id, source="JUDGE"
                        )

                    final_status = ArchiveReviewStatus.AI_APPROVED
                    auto_successes += 1
                    logger.success(f"✅ Auto-Resolved as {decision.winner} (Confidence: {decision.confidence:.2f})")

                except Exception as db_error:
                    logger.error(f"❌ Database error trying to auto-resolve '{row.tag_name}': {db_error}")
                    failures += 1
                    final_status = ArchiveReviewStatus.NEEDS_REVIEW  # Forces it to human review
                    decision.reason = f"FALHA NO BANCO: {db_error} | " + decision.reason
            else:
                sent_to_review += 1
                logger.warning(f"⚠️ Doubt! Confidence: {decision.confidence:.2f} | Reason: {decision.reason}")

            # 6. Log Writing in the Generic Review Queue (read by the curation inbox and the screens)
            new_log = ArchiveAIReviewQueue(
                anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
                status=final_status,
                context_payload={
                    "tag_id": row.tag_id,
                    "tag_name": row.tag_name,
                    "entity_id": row.entity_id,
                    "entity_name": row.entity_name,
                    "entity_type": row.entity_type,
                },
                llm_decision=decision.winner,
                llm_confidence=decision.confidence,
                llm_reason=decision.reason,
            )

            db.add(new_log)
            # Iterative commit: If the script is interrupted midway (Timeout/OOM),
            # we do not lose the dozens of evaluations the AI already processed.
            uow.commit()

        except Exception as e:
            logger.error(f"❌ Severe error processing the conflict '{row.tag_name}': {e}")
            uow.rollback()
            failures += 1
            continue

    logger.info(f"🏁 AI Judge finished. Total processed: {auto_successes + sent_to_review + failures}")
    logger.info(
        f"📊 Auto-resolved (Expunged): {auto_successes} | Human Queue: {sent_to_review} | Technical failures: {failures}"
    )


if __name__ == "__main__":
    with get_db() as db_session:
        execute(db_session)

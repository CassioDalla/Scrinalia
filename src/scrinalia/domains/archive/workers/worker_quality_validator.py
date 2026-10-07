"""
Structural anomaly validator (Fase 3.5-C).

The deterministic part of the review: no model is loaded unless an archivist registered an
active ``LLM_CHECK`` rule, and the regexes the curation wrote are applied as they were
registered. The worker never rewrites a field — it marks the document, records why and
sends it to human review, which is the only place the fix can happen.
"""

import re
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.archive.engines.base import TitleQualityEngine
from scrinalia.domains.archive.models import (
    AnomalyReason,
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveReviewStatus,
)
from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository
from scrinalia.domains.archive.repository.governance import ai_writable_documents
from scrinalia.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    effective_column_sql,
)
from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleDTO
from scrinalia.domains.archive.worker_stamp import QUALITY_VALIDATOR

#: Titles that appear at least this many times are suspicious as a template leftover.
DEFAULT_REPEAT_THRESHOLD = 3

#: A title shorter than this carries no information ("S/N", "Doc").
MIN_TITLE_LENGTH = 3

#: Below this confidence the language-model opinion is ignored, not queued.
DEFAULT_LLM_CONFIDENCE = 0.6

#: Placeholders the staging layer writes when the source had no title at all.
EMPTY_TITLE_VALUES = {"", "sem título", "sem titulo", "-"}


def _compile_rules(rules: list[CleaningRuleDTO]) -> list[tuple[CleaningRuleDTO, re.Pattern]]:
    compiled: list[tuple[CleaningRuleDTO, re.Pattern]] = []
    for rule in rules:
        try:
            compiled.append((rule, re.compile(rule.regex_pattern, re.IGNORECASE)))
        except re.error as e:
            logger.error(f"❌ Rule {rule.rule_id} ('{rule.rule_name}') has invalid Regex syntax: {e}. Skipping.")
    return compiled


def load_repeated_titles(db: Session, threshold: int) -> set[str]:
    """Titles shared by at least ``threshold`` documents, normalized to lowercase."""
    stmt = (
        select(func.lower(func.btrim(ArchiveDocument.original_title)))
        .group_by(func.lower(func.btrim(ArchiveDocument.original_title)))
        .having(func.count() >= threshold)
    )
    return set(db.scalars(stmt).all())


def evaluate_document(
    doc: ArchiveDocument,
    effective_title: str | None,
    effective_scope: str | None,
    has_tags: bool,
    has_entities: bool,
    repeated_titles: set[str],
    validate_rules: list[tuple[CleaningRuleDTO, re.Pattern]],
    llm_engine: TitleQualityEngine | None,
    llm_confidence: float,
    today: date,
) -> list[str]:
    """
    Returns the anomaly codes of one document; empty means "nothing to review".

    Kept as a pure function of its inputs so every rule is unit-testable without a
    database, and so the order of the reasons is stable (tests and the front-end read it).
    The relation flags arrive as booleans because the caller resolved them without N+1.
    """
    reasons: list[str] = []

    if doc.document_date is None:
        reasons.append(AnomalyReason.MISSING_DATE)
    elif doc.document_date > today:
        reasons.append(AnomalyReason.FUTURE_DATE)

    raw_title = (doc.original_title or "").strip()
    normalized_title = raw_title.lower()

    if normalized_title in EMPTY_TITLE_VALUES or len(raw_title) < MIN_TITLE_LENGTH:
        reasons.append(AnomalyReason.EMPTY_TITLE)
    else:
        if normalized_title in repeated_titles:
            reasons.append(AnomalyReason.REPEATED_TITLE)
        if raw_title == raw_title.upper() and len(raw_title) >= 10 and len(raw_title.split()) >= 2:
            reasons.append(AnomalyReason.ALL_CAPS_TITLE)
        # The title was nothing but an approved fixed template: the specific part is missing.
        if effective_title is not None and not effective_title.strip() and doc.original_title:
            reasons.append(AnomalyReason.TITLE_ONLY_TEMPLATE)

    if (doc.scope_content or "").strip() and effective_scope is not None and not effective_scope.strip():
        reasons.append(AnomalyReason.SCOPE_ONLY_BOILERPLATE)

    if not has_tags:
        reasons.append(AnomalyReason.NO_TAGS)
    if doc.typology_id is None:
        reasons.append(AnomalyReason.NO_TYPOLOGY)
    if not has_entities:
        reasons.append(AnomalyReason.NO_ENTITIES)

    for rule, pattern in validate_rules:
        value = getattr(doc, rule.target_column, None)
        if value and pattern.search(str(value)):
            label = rule.anomaly_reason or rule.rule_name
            reasons.append(f"{AnomalyReason.RULE_MATCH}:{label}")

    if llm_engine is not None and raw_title:
        decision = llm_engine.check_title(raw_title)
        if decision.is_suspect and decision.confidence >= llm_confidence:
            reasons.append(f"{AnomalyReason.LLM_SUSPECT}:{decision.reason}")

    return reasons


def pending_conditions(force: bool = False) -> list[ColumnElement[bool]]:
    """
    Predicate of the quality-validator queue, shared by ``execute`` and the operations panel.

    ``force`` re-reads every ai-writable document; the default only reads the ones without the
    stamp, so a second run of the worker is free.
    """
    if force:
        return [ai_writable_documents()]
    return [
        ai_writable_documents(),
        or_(
            ArchiveDocument.execution_log.is_(None),
            ~ArchiveDocument.execution_log.has_key(QUALITY_VALIDATOR.key),
        ),
    ]


def count_pending(db: Session, force: bool = False, **options: Any) -> int:
    """Documents the next validation run would read."""
    stmt = select(func.count()).select_from(ArchiveDocument).where(*pending_conditions(force))
    return int(db.scalar(stmt) or 0)


def execute(
    db: Session,
    db_batch_size: int = 64,
    force: bool = False,
    repeat_threshold: int = DEFAULT_REPEAT_THRESHOLD,
    llm_confidence: float = DEFAULT_LLM_CONFIDENCE,
    **engine_kwargs: Any,
) -> None:
    """
    Marks documents whose data cannot be trusted as it stands.

    Every document is stamped, with or without anomalies, so the queue advances. A
    ``HUMAN_APPROVED`` document is never touched: a human already looked at it.

    The language model is only built when an active ``LLM_CHECK`` rule exists — the
    default is deterministic validation at zero model cost.
    """
    logger.info("🚀 Starting the Quality Validator Worker")

    repository = CleaningRepository(db)
    validate_rules = _compile_rules([r for r in repository.get_active_rules() if r.rule_kind == "VALIDATE"])
    llm_rules = [r for r in repository.get_active_rules() if r.rule_kind == "LLM_CHECK"]

    text_repository = TextQualityRepository(db)
    title_rules = text_repository.get_active_rules("TITLE")
    text_rules = text_repository.get_active_rules("EMBEDDING")

    llm_engine: TitleQualityEngine | None = None
    if llm_rules:
        from scrinalia.domains.archive.engines.title_quality.registry import get_engine

        rule = llm_rules[0]
        logger.info(f"🤖 LLM title check enabled by rule '{rule.rule_name}' ({rule.engine_name or 'default'}).")
        llm_engine = get_engine(
            rule.engine_name or "ollama_title_check",  # type: ignore[arg-type]
            rule.preset,  # type: ignore[arg-type]
            **engine_kwargs,
        )
    else:
        logger.info("🧮 Deterministic validation only: no active LLM_CHECK rule.")

    repeated_titles = load_repeated_titles(db, repeat_threshold)
    logger.info(f"📋 {len(validate_rules)} validation rule(s); {len(repeated_titles)} repeated title(s).")

    effective_title_sql = effective_column_sql("original_title", title_rules)
    effective_scope_sql = effective_column_sql("scope_content", text_rules)
    has_tags = (
        select(ArchiveDocumentTag.description_id)
        .where(ArchiveDocumentTag.description_id == ArchiveDocument.description_id)
        .exists()
    )
    has_entities = (
        select(ArchiveDocumentEntity.description_id)
        .where(ArchiveDocumentEntity.description_id == ArchiveDocument.description_id)
        .exists()
    )

    where_cond: list[ColumnElement[bool]] = pending_conditions(force)

    pending = db.scalar(select(func.count()).select_from(ArchiveDocument).where(*where_cond))
    if not pending:
        logger.info("✨ No pending document found. Finishing.")
        return

    logger.info(f"🔍 Found {pending} documents to validate.")

    processed = 0
    total_anomalies = 0
    today = date.today()
    uow = UnitOfWork(db)

    while True:
        try:
            stmt = (
                select(
                    ArchiveDocument,
                    effective_title_sql.label("effective_title"),
                    effective_scope_sql.label("effective_scope"),
                    has_tags.label("has_tags"),
                    has_entities.label("has_entities"),
                )
                .where(*where_cond)
                .order_by(ArchiveDocument.description_id)
                .limit(db_batch_size)
            )
            rows = db.execute(stmt).all()
            if not rows:
                break

            for doc, effective_title, effective_scope, has_tags_value, has_entities_value in (
                (row[0], row[1], row[2], row[3], row[4]) for row in rows
            ):
                reasons = evaluate_document(
                    doc=doc,
                    effective_title=effective_title,
                    effective_scope=effective_scope,
                    has_tags=bool(has_tags_value),
                    has_entities=bool(has_entities_value),
                    repeated_titles=repeated_titles,
                    validate_rules=validate_rules,
                    llm_engine=llm_engine,
                    llm_confidence=llm_confidence,
                    today=today,
                )

                doc.is_anomaly = bool(reasons)
                doc.anomaly_reasons = reasons or None
                if reasons:
                    total_anomalies += 1
                    if doc.review_status in (ArchiveReviewStatus.PENDING_AI, ArchiveReviewStatus.AI_APPROVED):
                        doc.review_status = ArchiveReviewStatus.NEEDS_REVIEW

                doc.execution_log = QUALITY_VALIDATOR.mark(doc.execution_log)
                flag_modified(doc, "execution_log")
                processed += 1

            uow.commit()
            logger.info(f"⏳ Partial progress: {processed} documents validated ({total_anomalies} with anomalies).")
            db.expunge_all()

        except Exception as e:
            logger.error(f"💥 Failure validating a batch: {e}")
            uow.rollback()
            break

    logger.success(f"✅ Quality Validator finished! Validated: {processed} | With anomalies: {total_anomalies}.")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db)

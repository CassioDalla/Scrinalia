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

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.archive.engines.base import TitleQualityEngine
from scrinalia.domains.archive.models import (
    ANOMALY_REASON_SEPARATOR,
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
from scrinalia.domains.archive.worker_stamp import (
    QUALITY_VALIDATOR,
    identity_stamp_conditions,
    producer_fingerprint,
)
from scrinalia.domains.archive.workers.run_budget import RunBudget

#: Titles that appear at least this many times are suspicious as a template leftover.
DEFAULT_REPEAT_THRESHOLD = 3

#: A title shorter than this carries no information ("S/N", "Doc").
MIN_TITLE_LENGTH = 3

#: Below this confidence the language-model opinion is ignored, not queued.
DEFAULT_LLM_CONFIDENCE = 0.6

#: Placeholders the staging layer writes when the source had no title at all.
EMPTY_TITLE_VALUES = {"", "sem título", "sem titulo", "-"}


def compile_rules(rules: list[CleaningRuleDTO]) -> list[tuple[CleaningRuleDTO, re.Pattern]]:
    """The catalogue rules with their regex compiled, skipping the ones whose pattern does not build."""
    compiled: list[tuple[CleaningRuleDTO, re.Pattern]] = []
    for rule in rules:
        try:
            compiled.append((rule, re.compile(rule.regex_pattern, re.IGNORECASE)))
        except re.error as e:
            logger.error(f"❌ Rule {rule.rule_id} ('{rule.rule_name}') has invalid Regex syntax: {e}. Skipping.")
    return compiled


def rule_flag_label(rule: CleaningRuleDTO) -> str:
    """
    The label a ``VALIDATE`` rule's flag carries in ``anomaly_reasons``.

    The label the curator declared (``anomaly_reason``) when there is one, the rule's own name
    otherwise. Named because three readers now group by it: the worker that writes the flag, the
    facet that buckets it, and the bench that scores the rule against a human verdict.
    """
    return rule.anomaly_reason or rule.rule_name


def matched_rule_labels(doc: ArchiveDocument, validate_rules: list[tuple[CleaningRuleDTO, re.Pattern]]) -> list[str]:
    """
    Labels of the ``VALIDATE`` rules this document matches, in catalogue order.

    The one definition of "does this rule fire", shared by :func:`evaluate_document` and the bench:
    a bench that re-implemented the match would score a rule the worker does not have, and the
    difference would only show up as a precision the installation never had.
    """
    labels: list[str] = []
    for rule, pattern in validate_rules:
        value = getattr(doc, rule.target_column, None)
        if value and pattern.search(str(value)):
            labels.append(rule_flag_label(rule))
    return labels


def llm_check_reason(doc: ArchiveDocument, llm_engine: TitleQualityEngine | None, llm_confidence: float) -> str | None:
    """
    The reason the active ``LLM_CHECK`` rule adds for this document, or ``None``.

    Apart from :func:`evaluate_document` so the bench asks the same question with the same floor,
    instead of retyping ``is_suspect and confidence >= floor`` next to a model call.
    """
    raw_title = (doc.original_title or "").strip()
    if llm_engine is None or not raw_title:
        return None
    decision = llm_engine.check_title(raw_title)
    if decision.is_suspect and decision.confidence >= llm_confidence:
        return f"{AnomalyReason.LLM_SUSPECT}{ANOMALY_REASON_SEPARATOR}{decision.reason}"
    return None


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

    for label in matched_rule_labels(doc, validate_rules):
        reasons.append(f"{AnomalyReason.RULE_MATCH}{ANOMALY_REASON_SEPARATOR}{label}")

    llm_reason = llm_check_reason(doc, llm_engine, llm_confidence)
    if llm_reason is not None:
        reasons.append(llm_reason)

    return reasons


def active_llm_check_rule(db: Session) -> CleaningRuleDTO | None:
    """
    The rule that decides the engine of this worker, or ``None`` when there is no model.

    Defined once so ``execute``, ``count_pending`` and the operations panel cannot disagree about
    *which* rule the identity comes from. The panel refuses to let a person override the engine
    here for the same reason: a second place to choose it would be a second source of truth.
    """
    rules = CleaningRepository(db).get_active_rules("LLM_CHECK")
    return rules[0] if rules else None


def producer_identity(
    db: Session,
    *,
    repeat_threshold: int,
    llm_confidence: float,
    engine_kwargs: dict,
) -> str:
    """
    Identity of the validator: the engine of the active ``LLM_CHECK`` rule and its own thresholds.

    With no active rule there is no model, and the identity says so — which is why *activating* a
    rule re-queues the collection: the verdict changes from deterministic validation to one that
    also asks a language model.
    """
    from scrinalia.domains.archive.engines.title_quality.registry import describe_config

    rule = active_llm_check_rule(db)
    # The rule carries free text, not the registry's Literals; ``execute`` resolves the same pair
    # with the same fallback before calling ``get_engine``.
    engine_name = (rule.engine_name or "ollama_title_check") if rule is not None else None
    preset = rule.preset if rule is not None else None
    config = describe_config(engine_name, preset, **engine_kwargs) if engine_name else {}  # type: ignore[arg-type]
    return producer_fingerprint(
        axis="title_quality",
        engine_name=engine_name,
        preset=preset,
        engine_config=config,
        worker_options={"repeat_threshold": repeat_threshold, "llm_confidence": llm_confidence},
    )


def pending_conditions(producer: str, force: bool = False) -> list[ColumnElement[bool]]:
    """
    Predicate of the quality-validator queue, shared by ``execute`` and the operations panel.

    ``force`` re-reads every ai-writable document; the default only reads the ones the current
    producer has not stamped, so a second run of the worker is free. The identity is the engine of
    the active ``LLM_CHECK`` rule and the thresholds, so editing the rule re-queues the collection
    without a person having to remember to.
    """
    conditions: list[ColumnElement[bool]] = [ai_writable_documents()]
    conditions.extend(
        identity_stamp_conditions(ArchiveDocument.execution_log, QUALITY_VALIDATOR, producer, force=force)
    )
    return conditions


def count_pending(
    db: Session,
    force: bool = False,
    repeat_threshold: int = DEFAULT_REPEAT_THRESHOLD,
    llm_confidence: float = DEFAULT_LLM_CONFIDENCE,
    **engine_kwargs: Any,
) -> int:
    """Documents the next validation run would read, under the identity it would write."""
    identity = producer_identity(
        db,
        repeat_threshold=repeat_threshold,
        llm_confidence=llm_confidence,
        engine_kwargs=engine_kwargs,
    )
    stmt = select(func.count()).select_from(ArchiveDocument).where(*pending_conditions(identity, force=force))
    return int(db.scalar(stmt) or 0)


def execute(
    db: Session,
    db_batch_size: int = 64,
    force: bool = False,
    limit: int | None = None,
    repeat_threshold: int = DEFAULT_REPEAT_THRESHOLD,
    llm_confidence: float = DEFAULT_LLM_CONFIDENCE,
    **engine_kwargs: Any,
) -> None:
    """
    Marks documents whose data cannot be trusted as it stands.

    Every document is stamped with the **identity of the producer**, with or without anomalies, so
    the queue advances; a document validated with another engine or threshold is pending again. A
    ``HUMAN_APPROVED`` document is never touched: a human already looked at it.

    The language model is only built when an active ``LLM_CHECK`` rule exists — the
    default is deterministic validation at zero model cost.

    The loop advances by a ``description_id`` cursor. Without it a forced run would re-read the
    same first batch forever, because ``force`` drops the only clause that used to make a
    document leave the queue.

    Args:
        db (Session): Database session.
        db_batch_size (int, optional): Documents fetched and committed per transaction.
        force (bool, optional): Re-reads every ai-writable document instead of only the ones this
            producer has not stamped; the reasons also depend on the catalog, which a hash of the
            engine cannot see. Default is ``False``.
        limit (int | None, optional): Cap on the documents this run touches. Not persisted.
        repeat_threshold (int, optional): How many equal titles make a template leftover.
        llm_confidence (float, optional): Below this the language-model opinion is ignored.
        **engine_kwargs (Any): Extra keyword arguments forwarded to the title-quality engine.
    """
    logger.info("🚀 Starting the Quality Validator Worker")

    repository = CleaningRepository(db)
    validate_rules = compile_rules([r for r in repository.get_active_rules() if r.rule_kind == "VALIDATE"])
    llm_rules = repository.get_active_rules("LLM_CHECK")

    text_repository = TextQualityRepository(db)
    title_rules = text_repository.get_active_rules("TITLE")
    text_rules = text_repository.get_active_rules("EMBEDDING")

    identity = producer_identity(
        db,
        repeat_threshold=repeat_threshold,
        llm_confidence=llm_confidence,
        engine_kwargs=engine_kwargs,
    )
    logger.info(f"🔖 Producer identity: {identity[:12]}")

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

    where_cond: list[ColumnElement[bool]] = pending_conditions(identity, force=force)

    pending = db.scalar(select(func.count()).select_from(ArchiveDocument).where(*where_cond))
    if not pending:
        logger.info("✨ No pending document found. Finishing.")
        return

    logger.info(f"🔍 Found {pending} documents to validate.")

    processed = 0
    total_anomalies = 0
    today = date.today()
    last_id = ""
    budget = RunBudget(limit)
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
                .where(*where_cond, ArchiveDocument.description_id > last_id)
                .order_by(ArchiveDocument.description_id)
                .limit(budget.batch_size(db_batch_size))
            )
            rows = db.execute(stmt).all()
            if not rows:
                break

            last_id = rows[-1][0].description_id
            budget.spend(len(rows))

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

                doc.execution_log = QUALITY_VALIDATOR.mark_value(doc.execution_log, identity)
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

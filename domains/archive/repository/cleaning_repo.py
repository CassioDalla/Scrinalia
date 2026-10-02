from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.archive.models import ArchiveCleaningRule, ArchiveDocument, ArchiveReviewStatus
from domains.archive.schemas.cleaning_schema import CleaningRuleDTO
from domains.archive.worker_stamp import cleaning_rule_stamp


class CleaningRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_rule(self, rule_data: dict) -> CleaningRuleDTO:
        rule = ArchiveCleaningRule(**rule_data)
        self.db.add(rule)
        self.db.flush()
        return CleaningRuleDTO.model_validate(rule, from_attributes=True)

    def get_active_rules(self) -> Sequence[CleaningRuleDTO]:
        stmt = select(ArchiveCleaningRule).where(ArchiveCleaningRule.is_active.is_(True))
        return [CleaningRuleDTO.model_validate(rule, from_attributes=True) for rule in self.db.scalars(stmt).all()]

    def get_rule_by_id(self, rule_id: int) -> CleaningRuleDTO | None:
        stmt = select(ArchiveCleaningRule).where(ArchiveCleaningRule.rule_id == rule_id)
        rule = self.db.scalars(stmt).one_or_none()
        return CleaningRuleDTO.model_validate(rule, from_attributes=True) if rule else None

    def deactivate_rule(self, rule_id: int) -> CleaningRuleDTO | None:
        """Marks the rule as inactive and returns it; the caller owns the commit."""
        rule = self.db.scalars(select(ArchiveCleaningRule).where(ArchiveCleaningRule.rule_id == rule_id)).one_or_none()
        if rule is None:
            return None

        rule.is_active = False
        self.db.flush()
        return CleaningRuleDTO.model_validate(rule, from_attributes=True)

    def get_unprocessed_documents_for_rule(
        self, rule_id: int, target_column: str, limit: int = 500
    ) -> Sequence[ArchiveDocument]:
        """
        Fetches documents that DO NOT YET have the 'rule_X' flag in execution_log
        and where the target column is NOT null.

        Documents validated by a human (``HUMAN_APPROVED``) are excluded: the AI must
        never overwrite a human's decision.
        """
        rule_key = cleaning_rule_stamp(rule_id).key

        stmt = (
            select(ArchiveDocument)
            .where(getattr(ArchiveDocument, target_column).is_not(None))
            .where(ArchiveDocument.review_status != ArchiveReviewStatus.HUMAN_APPROVED)
            .where(
                # Either the log does not exist, or if it does, it does not contain the rule key
                (ArchiveDocument.execution_log.is_(None)) | (~ArchiveDocument.execution_log.has_key(rule_key))
            )
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def get_random_sample_for_dry_run(self, target_column: str, limit: int = 200) -> Sequence[ArchiveDocument]:
        """Fetches a sample of non-null documents to try to find matches for the Dry-Run."""
        stmt = (
            select(ArchiveDocument)
            .where(getattr(ArchiveDocument, target_column).is_not(None))
            .where(ArchiveDocument.review_status != ArchiveReviewStatus.HUMAN_APPROVED)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

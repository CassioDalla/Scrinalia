from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.archive.models import ArchiveCleaningRule, ArchiveDocument


class CleaningRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_rule(self, rule_data: dict) -> ArchiveCleaningRule:
        rule = ArchiveCleaningRule(**rule_data)
        self.db.add(rule)
        self.db.flush()
        return rule

    def get_active_rules(self) -> Sequence[ArchiveCleaningRule]:
        stmt = select(ArchiveCleaningRule).where(ArchiveCleaningRule.is_active.is_(True))
        return self.db.scalars(stmt).all()

    def get_rule_by_id(self, rule_id: int) -> ArchiveCleaningRule:
        stmt = select(ArchiveCleaningRule).where(ArchiveCleaningRule.rule_id == rule_id)
        return self.db.scalars(stmt).one()

    def get_unprocessed_documents_for_rule(
        self, rule_id: int, target_column: str, limit: int = 500
    ) -> Sequence[ArchiveDocument]:
        """
        Fetches documents that DO NOT YET have the 'rule_X' flag in execution_log
        and where the target column is NOT null.
        """
        rule_key = f"cleaning_rule_{rule_id}"

        stmt = (
            select(ArchiveDocument)
            .where(getattr(ArchiveDocument, target_column).is_not(None))
            .where(
                # Either the log does not exist, or if it does, it does not contain the rule key
                (ArchiveDocument.execution_log.is_(None)) | (~ArchiveDocument.execution_log.has_key(rule_key))
            )
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def get_random_sample_for_dry_run(self, target_column: str, limit: int = 200) -> Sequence[ArchiveDocument]:
        """Fetches a sample of non-null documents to try to find matches for the Dry-Run."""
        stmt = select(ArchiveDocument).where(getattr(ArchiveDocument, target_column).is_not(None)).limit(limit)
        return self.db.scalars(stmt).all()

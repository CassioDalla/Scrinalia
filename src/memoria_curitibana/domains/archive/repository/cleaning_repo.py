from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql.elements import ColumnElement

from memoria_curitibana.domains.archive.domain.governance import DocumentWritePolicy
from memoria_curitibana.domains.archive.models import ArchiveCleaningRule, ArchiveDocument
from memoria_curitibana.domains.archive.repository.governance import ai_writable_documents
from memoria_curitibana.domains.archive.schemas.cleaning_schema import (
    AllowedColumns,
    CleanableDocumentDTO,
    CleaningRuleCreateDTO,
    CleaningRuleDTO,
    CleaningUpdateCommand,
    RuleKind,
)
from memoria_curitibana.domains.archive.worker_stamp import cleaning_rule_stamp


class CleaningRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_rule(self, rule_data: CleaningRuleCreateDTO) -> CleaningRuleDTO:
        rule = ArchiveCleaningRule(**rule_data.model_dump())
        self.db.add(rule)
        self.db.flush()
        return CleaningRuleDTO.model_validate(rule, from_attributes=True)

    def get_active_rules(self, rule_kind: RuleKind | None = None) -> Sequence[CleaningRuleDTO]:
        """
        Active rules, optionally restricted to one kind.

        The filter is not a convenience: the cleaning worker must only see ``REWRITE``
        rules, otherwise a validation rule would rewrite the text with its replacement.
        """
        stmt = select(ArchiveCleaningRule).where(ArchiveCleaningRule.is_active.is_(True))
        if rule_kind is not None:
            stmt = stmt.where(ArchiveCleaningRule.rule_kind == rule_kind)
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

    def _unprocessed_conditions(self, rule_id: int, target_column: AllowedColumns) -> list[ColumnElement[bool]]:
        """
        The predicate of "this document still has to see this rule", defined once.

        Both the batch read and the panel's count go through here, so a change to the governance
        rule cannot make the screen disagree with the worker.
        """
        rule_key = cleaning_rule_stamp(rule_id).key
        column = getattr(ArchiveDocument, target_column)
        return [
            column.is_not(None),
            ai_writable_documents(),
            # Either the log does not exist, or if it does, it does not contain the rule key.
            (ArchiveDocument.execution_log.is_(None)) | (~ArchiveDocument.execution_log.has_key(rule_key)),
        ]

    def get_unprocessed_documents_for_rule(
        self, rule_id: int, target_column: AllowedColumns, limit: int = 500
    ) -> Sequence[CleanableDocumentDTO]:
        """
        Fetches documents that DO NOT YET have the 'rule_X' flag in execution_log
        and where the target column is NOT null.

        Documents validated by a human (``HUMAN_APPROVED``) are excluded: the AI must
        never overwrite a human's decision.
        """
        column = getattr(ArchiveDocument, target_column)
        stmt = (
            select(ArchiveDocument.description_id, column.label("text"))
            .where(*self._unprocessed_conditions(rule_id, target_column))
            .limit(limit)
        )
        return [CleanableDocumentDTO.model_validate(row._mapping) for row in self.db.execute(stmt)]

    def count_unprocessed_documents_for_rule(self, rule_id: int, target_column: AllowedColumns) -> int:
        """How many documents the next pass of one rule would read."""
        stmt = (
            select(func.count())
            .select_from(ArchiveDocument)
            .where(*self._unprocessed_conditions(rule_id, target_column))
        )
        return int(self.db.scalar(stmt) or 0)

    def get_random_sample_for_dry_run(
        self, target_column: AllowedColumns, limit: int = 200
    ) -> Sequence[CleanableDocumentDTO]:
        """Fetches a sample of non-null documents to try to find matches for the Dry-Run."""
        column = getattr(ArchiveDocument, target_column)
        stmt = (
            select(ArchiveDocument.description_id, column.label("text"))
            .where(column.is_not(None))
            .where(ai_writable_documents())
            .limit(limit)
        )
        return [CleanableDocumentDTO.model_validate(row._mapping) for row in self.db.execute(stmt)]

    def apply_cleaning(self, updates: Sequence[CleaningUpdateCommand]) -> None:
        """
        Applies a batch of column replacements and rule stamps.

        The rows are loaded by description_id (usually already in the identity map
        after the scan) and mutated in place; the caller owns the commit.
        """
        if not updates:
            return

        updates_by_id = {update.description_id: update for update in updates}
        documents = self.db.scalars(
            select(ArchiveDocument).where(ArchiveDocument.description_id.in_(updates_by_id))
        ).all()

        for doc in documents:
            if not DocumentWritePolicy.can_ai_write(doc.review_status):
                # A human approved the document after the scan; never overwrite human curation.
                continue

            update = updates_by_id[doc.description_id]
            setattr(doc, update.target_column, update.new_text)

            current_log = dict(doc.execution_log) if doc.execution_log else {}
            current_log[update.stamp_key] = "DONE"
            doc.execution_log = current_log
            flag_modified(doc, "execution_log")

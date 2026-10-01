from sqlalchemy import select, update
from sqlalchemy.orm import Session
from typing import Sequence

from domains.archive.models import ArchiveDocument, ArchiveCleaningRule


class CleaningRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_rule(self, rule_data: dict) -> ArchiveCleaningRule:
        rule = ArchiveCleaningRule(**rule_data)
        self.db.add(rule)
        self.db.flush()
        return rule

    def get_active_rules(self) -> Sequence[ArchiveCleaningRule]:
        stmt = select(ArchiveCleaningRule).where(ArchiveCleaningRule.is_active == True)
        return self.db.scalars(stmt).all()

    def get_rule_by_id(self, rule_id: int) -> ArchiveCleaningRule:
        stmt = select(ArchiveCleaningRule).where(ArchiveCleaningRule.rule_id == rule_id)
        return self.db.scalars(stmt).one()

    def get_unprocessed_documents_for_rule(
        self, rule_id: int, target_column: str, limit: int = 500
    ) -> Sequence[ArchiveDocument]:
        """
        Busca documentos que AINDA NÃO têm a flag 'rule_X' no execution_log
        e onde a coluna alvo NÃO é nula.
        """
        rule_key = f"cleaning_rule_{rule_id}"

        stmt = (
            select(ArchiveDocument)
            .where(getattr(ArchiveDocument, target_column).is_not(None))
            .where(
                # Ou o log não existe, ou se existe, não contém a chave da regra
                (ArchiveDocument.execution_log.is_(None)) | (~ArchiveDocument.execution_log.has_key(rule_key))
            )
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def get_random_sample_for_dry_run(self, target_column: str, limit: int = 200) -> Sequence[ArchiveDocument]:
        """Busca uma amostra de documentos não-nulos para tentar achar matches para o Dry-Run."""
        stmt = select(ArchiveDocument).where(getattr(ArchiveDocument, target_column).is_not(None)).limit(limit)
        return self.db.scalars(stmt).all()

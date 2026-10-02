from collections.abc import Sequence
from typing import Protocol

from domains.archive.models import ArchiveDocument
from domains.archive.schemas.cleaning_schema import CleaningRuleDTO


class CleaningRepositoryPort(Protocol):
    """
    Output port for the dynamic cleaning rules.

    Rule reads return `CleaningRuleDTO`. The document-fetching methods still
    return ORM entities because the cleaning worker mutates their columns;
    a command/result DTO for that write path is a known debt
    (see `.analysis/adr-arquitetura-alvo.md`).
    """

    # --- Rule reads/writes ---
    def create_rule(self, rule_data: dict) -> CleaningRuleDTO: ...
    def get_active_rules(self) -> Sequence[CleaningRuleDTO]: ...
    def get_rule_by_id(self, rule_id: int) -> CleaningRuleDTO | None: ...
    def deactivate_rule(self, rule_id: int) -> CleaningRuleDTO | None: ...

    # --- Document scans (write-side ORM debt) ---
    def get_unprocessed_documents_for_rule(
        self, rule_id: int, target_column: str, limit: int = 500
    ) -> Sequence[ArchiveDocument]: ...
    def get_random_sample_for_dry_run(self, target_column: str, limit: int = 200) -> Sequence[ArchiveDocument]: ...

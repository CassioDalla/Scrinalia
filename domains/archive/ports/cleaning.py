from collections.abc import Sequence
from typing import Protocol

from domains.archive.schemas.cleaning_schema import (
    AllowedColumns,
    CleanableDocumentDTO,
    CleaningRuleCreateDTO,
    CleaningRuleDTO,
    CleaningUpdateCommand,
)


class CleaningRepositoryPort(Protocol):
    """
    Output port for the dynamic cleaning rules.

    Reads and writes cross the boundary as DTOs/commands; the SQLAlchemy
    entities never leave the adapter.
    """

    # --- Rule reads/writes ---
    def create_rule(self, rule_data: CleaningRuleCreateDTO) -> CleaningRuleDTO: ...
    def get_active_rules(self) -> Sequence[CleaningRuleDTO]: ...
    def get_rule_by_id(self, rule_id: int) -> CleaningRuleDTO | None: ...
    def deactivate_rule(self, rule_id: int) -> CleaningRuleDTO | None: ...

    # --- Document scans and updates ---
    def get_unprocessed_documents_for_rule(
        self, rule_id: int, target_column: AllowedColumns, limit: int = 500
    ) -> Sequence[CleanableDocumentDTO]: ...
    def get_random_sample_for_dry_run(
        self, target_column: AllowedColumns, limit: int = 200
    ) -> Sequence[CleanableDocumentDTO]: ...
    def apply_cleaning(self, updates: Sequence[CleaningUpdateCommand]) -> None: ...

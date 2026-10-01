from pydantic import BaseModel
from typing import Literal

AllowedColumns = Literal["original_title", "scope_content", "admin_bio_history", "provenance", "archivist_notes"]


class CleaningRuleCreateDTO(BaseModel):
    """DTO para criar uma regra."""

    rule_name: str
    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str
    created_by: str | None = None


class CleaningRuleDTO(CleaningRuleCreateDTO):
    """DTO representando uma regra ativa no banco."""

    rule_id: int
    is_active: bool


class DryRunRequestDTO(BaseModel):
    """DTO solicitando uma simulação."""

    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str


class DryRunMatchDTO(BaseModel):
    """DTO com o resultado de um match de simulação."""

    description_id: str
    original_text: str
    modified_text: str


class DryRunResponseDTO(BaseModel):
    """DTO com o laudo final da simulação (Dry-Run)."""

    is_valid_regex: bool
    error_message: str | None = None
    matches_found: int = 0
    samples: list[DryRunMatchDTO] = []

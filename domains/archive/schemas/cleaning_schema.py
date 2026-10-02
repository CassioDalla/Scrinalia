from typing import Literal

from pydantic import BaseModel, Field

AllowedColumns = Literal["original_title", "scope_content", "admin_bio_history", "provenance", "archivist_notes"]


class CleaningRuleCreateDTO(BaseModel):
    """DTO to create a rule."""

    rule_name: str
    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str
    created_by: str | None = None


class CleaningRuleDTO(CleaningRuleCreateDTO):
    """DTO representing an active rule in the database."""

    rule_id: int
    is_active: bool


class DryRunRequestDTO(BaseModel):
    """DTO requesting a simulation."""

    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str


class DryRunMatchDTO(BaseModel):
    """DTO with the result of a simulation match."""

    description_id: str
    original_text: str
    modified_text: str


class DryRunResponseDTO(BaseModel):
    """DTO with the final report of the simulation (Dry-Run)."""

    is_valid_regex: bool
    error_message: str | None = None
    matches_found: int = 0
    samples: list[DryRunMatchDTO] = []


class CleanableDocumentDTO(BaseModel):
    """Read view of a document that a cleaning rule may rewrite."""

    description_id: str
    text: str = Field(description="Current value of the rule's target column.")


class CleaningUpdateCommand(BaseModel):
    """Write command: replace the target column and stamp the rule in ``execution_log``."""

    description_id: str
    target_column: AllowedColumns
    new_text: str
    stamp_key: str

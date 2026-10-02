from typing import Literal

from pydantic import BaseModel, Field

# The columns the user is allowed to interact with in the Frontend
AllowedColumns = Literal["original_title", "scope_content", "admin_bio_history", "provenance", "archivist_notes"]


class CreateCleaningRuleRequest(BaseModel):
    """Payload received from the Frontend when the user clicks 'Save Rule'."""

    rule_name: str = Field(..., max_length=150, description="Identifying name of the rule.")
    target_column: AllowedColumns = Field(..., description="Target column for cleaning.")
    regex_pattern: str = Field(..., description="Python-compatible Regex pattern.")
    replacement_string: str = Field(default="", description="What to replace it with. Leave empty to delete.")


class DryRunRequest(BaseModel):
    """Payload received from the Frontend to test the 'Before and After' (Simulation)."""

    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str = ""

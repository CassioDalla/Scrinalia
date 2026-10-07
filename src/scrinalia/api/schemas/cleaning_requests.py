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
    rule_kind: Literal["REWRITE", "VALIDATE", "LLM_CHECK"] = Field(
        default="REWRITE",
        description="REWRITE replaces the match; VALIDATE only flags an anomaly; LLM_CHECK asks a model about the title.",
    )
    anomaly_reason: str | None = Field(
        default=None, description="Reason written to the document when a VALIDATE rule matches."
    )
    engine_name: str | None = Field(default=None, description="Engine used by an LLM_CHECK rule.")
    preset: str | None = Field(default=None, description="Preset used by an LLM_CHECK rule.")


class DryRunRequest(BaseModel):
    """Payload received from the Frontend to test the 'Before and After' (Simulation)."""

    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str = ""

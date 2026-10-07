from typing import Literal

from pydantic import BaseModel, Field

from memoria_curitibana.domains.archive.schemas.responses import RouteResponse

AllowedColumns = Literal["original_title", "scope_content", "admin_bio_history", "provenance", "archivist_notes"]

#: What a registered rule does. ``REWRITE`` is the original behaviour (the worker replaces
#: every match); ``VALIDATE`` only flags a match as an anomaly and never touches the text;
#: ``LLM_CHECK`` is the opt-in for a language-model opinion about the title.
RuleKind = Literal["REWRITE", "VALIDATE", "LLM_CHECK"]


class CleaningRuleCreateDTO(BaseModel):
    """DTO to create a rule."""

    rule_name: str
    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str
    rule_kind: RuleKind = "REWRITE"
    anomaly_reason: str | None = None
    engine_name: str | None = None
    preset: str | None = None
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


class CleaningRuleMutationResponse(RouteResponse):
    """
    Result of a write on the rule catalog.

    The route answered a plain ``dict`` until the curator front needed it; an untyped body is
    invisible to the generated client, so the screen would read it through a cast. ``kind`` matters
    to the reader: a ``VALIDATE``/``LLM_CHECK`` rule only flags, a ``REWRITE`` rule replaces text.
    """

    data: CleaningRuleDTO


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

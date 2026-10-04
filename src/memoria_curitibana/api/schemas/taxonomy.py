from typing import Literal

from pydantic import BaseModel, Field, model_validator

from memoria_curitibana.domains.archive.schemas.entity_schema import ConflictResolutionData, CrossDomainConflict


class MergeRequest(BaseModel):
    canonical_id: int
    ids_to_merge: list[int] = Field(min_length=1, description="List of IDs that will be merged and deleted.")
    new_name: str | None = None


class MergeSuggestionRequest(BaseModel):
    """Parameters of a suggestion run over the tag catalog."""

    threshold: float = Field(default=0.65, gt=0, le=1, description="pg_trgm similarity floor.")
    limit: int = Field(default=50, ge=1, le=500, description="How many clusters the run may register.")


class MergeProposalDecisionRequest(BaseModel):
    """The archivist's verdict on one proposed cluster. It records intent; it does not merge."""

    status: Literal["APPROVED", "REJECTED"]
    decided_by: str | None = Field(default=None, description="Who decided; free text until authentication exists.")
    note: str | None = Field(default=None, description="Why; kept for auditing.")


class MergePreviewRequest(BaseModel):
    """Dry-run of a merge, by persisted proposal or by an explicit canonical + ids."""

    proposal_id: int | None = None
    canonical_id: int | None = None
    ids_to_merge: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_source_of_truth(self) -> "MergePreviewRequest":
        if self.proposal_id is None and (self.canonical_id is None or not self.ids_to_merge):
            raise ValueError("informe 'proposal_id' ou 'canonical_id' com 'ids_to_merge'")
        if self.proposal_id is not None and (self.canonical_id is not None or self.ids_to_merge):
            raise ValueError("'proposal_id' não pode ser combinado com 'canonical_id'/'ids_to_merge'")
        return self


class StopwordsRequest(BaseModel):
    words: list[str] = Field(min_length=1, description="List of words to be banned.")


class SuggestMacroRequest(BaseModel):
    source_type: Literal["tags", "documents"] = Field(
        default="tags", description="The data source the AI will use to generate the clusters."
    )
    columns_to_extract: list[str] | None = None


class MacroCategoryCreateRequest(BaseModel):
    """Official macro category the curator creates from a suggested cluster."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(
        default=None, description="Context read by the classifier to tell similar categories apart."
    )


class MacroCategoryUpdateRequest(BaseModel):
    """Partial edit of a macro category."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    is_active: bool | None = None


class ReclassifyEntityRequest(BaseModel):
    new_type: Literal["ORG", "PER", "LOC"]


class NerExclusionRequest(BaseModel):
    """Terms a curator declares to belong to the subject axis, not to named entities."""

    words: list[str] = Field(min_length=1, description="Terms to keep out of the NER extraction.")
    reason: str | None = Field(default=None, description="Why the decision was made; kept for auditing.")


class ConflictResolutionResponse(BaseModel):
    message: str
    data: ConflictResolutionData


class CrossDomainConflictListResponse(BaseModel):
    data: list[CrossDomainConflict]


class ConflictResolutionRequest(BaseModel):
    winner: Literal["TAG", "ENTITY"]
    tag_id: int
    entity_id: int

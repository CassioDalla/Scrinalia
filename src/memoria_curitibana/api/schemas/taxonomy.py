from typing import Literal

from pydantic import BaseModel, Field

from memoria_curitibana.domains.archive.schemas.entity_schema import ConflictResolutionData, CrossDomainConflict


class MergeRequest(BaseModel):
    canonical_id: int
    ids_to_merge: list[int] = Field(min_length=1, description="List of IDs that will be merged and deleted.")
    new_name: str | None = None


class StopwordsRequest(BaseModel):
    words: list[str] = Field(min_length=1, description="List of words to be banned.")


class SuggestMacroRequest(BaseModel):
    source_type: Literal["tags", "documents"] = Field(
        default="tags", description="The data source the AI will use to generate the clusters."
    )
    columns_to_extract: list[str] | None = None


class ReclassifyEntityRequest(BaseModel):
    new_type: Literal["ORG", "PER", "LOC"]


class ConflictResolutionResponse(BaseModel):
    message: str
    data: ConflictResolutionData


class CrossDomainConflictListResponse(BaseModel):
    data: list[CrossDomainConflict]


class ConflictResolutionRequest(BaseModel):
    winner: Literal["TAG", "ENTITY"]
    tag_id: int
    entity_id: int

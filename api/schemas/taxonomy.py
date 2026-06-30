from typing import Literal

from pydantic import BaseModel, Field


class MergeRequest(BaseModel):
    canonical_id: int
    ids_to_merge: list[int] = Field(min_length=1, description="Lista de IDs que serão mesclados e deletados.")
    new_name: str | None = None


class StopwordsRequest(BaseModel):
    words: list[str] = Field(min_length=1, description="Lista de palavras a serem banidas.")


class SuggestMacroRequest(BaseModel):
    source_type: Literal["tags", "documents"] = Field(
        default="tags", description="A fonte de dados que a IA usará para gerar os clusters."
    )
    columns_to_extract: list[str] | None = None


class ReclassifyEntityRequest(BaseModel):
    new_type: Literal["ORG", "PER", "LOC"]

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TagRelevanceCount(BaseModel):
    name: str
    total_usage: int

    model_config = ConfigDict(from_attributes=True)


class TagRelevanceIdf(BaseModel):
    name: str
    frequency: float
    weight_idf: float
    score_tfidf: float

    model_config = ConfigDict(from_attributes=True)


class TagRelevanceResponse(BaseModel):
    mode: Literal["count", "tfidf"]
    payload: list[TagRelevanceCount | TagRelevanceIdf]

    @classmethod
    def from_payload(cls, payload: list[TagRelevanceCount | TagRelevanceIdf]) -> "TagRelevanceResponse":
        if not payload:
            return cls(mode="count", payload=[])

        first_item = payload[0]

        if isinstance(first_item, TagRelevanceCount):
            return cls(mode="count", payload=payload)

        elif isinstance(first_item, TagRelevanceIdf):
            return cls(mode="tfidf", payload=payload)

        raise ValueError("Tipo de payload desconhecido")


class TagSimilarity(BaseModel):
    tag_id: int
    name: str
    similarity: float

    model_config = ConfigDict(from_attributes=True)


# Think about a way to merge this with the schema above
class TagPairSimilarity(BaseModel):
    id_1: int
    name_1: str
    id_2: int
    name_2: str
    sim_score: float

    model_config = ConfigDict(from_attributes=True)


class MergeResponse(BaseModel):
    documents_updated: int
    tags_deleted: int

    model_config = ConfigDict(from_attributes=True)


class MacroCategorySuggested(BaseModel):
    topic_id: int
    suggested_name: str
    estimate_count: int
    real_samples: list[str] = Field(default_factory=list)


class MacroCategoriesSuggestionResponse(BaseModel):
    total_suggestions: int
    categories: list[MacroCategorySuggested]
    message: str | None = None


class ArchiveMacroCategoryEntityDTO(BaseModel):
    category_id: int
    name: str
    description: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ArchiveTagDTO(BaseModel):
    """
    Strict contract for creating Tags (Taxonomy).

    Ensures that the classification models (e.g. mDeBERTa) deliver
    consistent categories accompanied by their confidence metric
    for observability metrics.
    """

    name: str = Field(description="The associated keyword or concept, preferably in lowercase.")
    macro_category_id: int | None = Field(
        default=None, description="Id linking to the main semantic drawer (e.g. Urbanism, Health)"
    )
    ai_confidence_score: float | None = Field(
        default=None, description="Degree of certainty of the AI model (0.0 to 1.0 or 0 to 100)."
    )

    model_config = ConfigDict(from_attributes=True)

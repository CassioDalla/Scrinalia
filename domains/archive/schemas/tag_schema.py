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


# Pensar em alguma forma juntar com o schema de cima
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
    Contrato rigoroso para a criação de Tags (Taxonomia).

    Assegura que os modelos de classificação (ex: mDeBERTa) entreguem
    categorias consistentes acompanhadas de sua métrica de confiança
    para métricas de observabilidade.
    """

    name: str = Field(description="A palavra-chave ou conceito associado, preferencialmente em minúsculo.")
    macro_category_id: int | None = Field(
        default=None, description="Id linkando para a gaveta semântica principal (ex: Urbanismo, Saúde)"
    )
    ai_confidence_score: float | None = Field(
        default=None, description="Grau de certeza do modelo de IA (0.0 a 1.0 ou 0 a 100)."
    )

    model_config = ConfigDict(from_attributes=True)

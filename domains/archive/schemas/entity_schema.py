from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArchiveEntityDTO(BaseModel):
    """
    Contrato de dados para Entidades Nomeadas (NER).

    Garante que os extratores (como o spaCy) retornem entidades
    padronizadas e validadas contra os tipos permitidos no domínio
    antes da persistência.
    """

    name: str = Field(description="Nome limpo e formatado da entidade.")
    entity_type: Literal["PER", "ORG", "LOC"] = Field(
        description="Tipo da entidade. Restrito a Pessoa, Organização ou Local."
    )

    model_config = ConfigDict(from_attributes=True)


class EntitySimilarity(BaseModel):
    entity_id: int
    name: str
    entity_type: str
    similarity: float

    model_config = ConfigDict(from_attributes=True)


class EntityPairSimilarity(BaseModel):
    id_1: int
    name_1: str
    type_1: str
    id_2: int
    name_2: str
    type_2: str
    similarity: float

    model_config = ConfigDict(from_attributes=True)


class EntityMergeResponse(BaseModel):
    documents_updated: int
    entities_deleted: int

    model_config = ConfigDict(from_attributes=True)


class EntityRelevance(BaseModel):
    entity_id: int
    name: str
    entity_type: str
    total_usage: int

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from memoria_curitibana.domains.archive.schemas.types import EntityName


class NerSynonymRule(TypedDict):
    """
    Phrase pattern fed to spaCy's EntityRuler.

    ``pattern`` is the synonym spelling, ``label`` is the entity type and ``id``
    is the canonical entity name that spaCy exposes as ``ent_id_``.
    """

    pattern: str
    label: str
    id: str


class ArchiveEntityDTO(BaseModel):
    """
    Data contract for Named Entities (NER).

    Ensures that the extractors (such as spaCy) return entities
    standardized and validated against the types allowed in the domain
    before persistence.
    """

    name: EntityName = Field(description="Clean, formatted name of the entity.")
    entity_type: Literal["PER", "ORG", "LOC"] = Field(
        description="Entity type. Restricted to Person, Organization or Location."
    )

    model_config = ConfigDict(from_attributes=True)


class EntityIdentity(BaseModel):
    """Lightweight read view of an entity used by write-side flows (merge, lookups)."""

    entity_id: int
    name: str
    entity_type: str

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


class EntitySimilarityResponse(BaseModel):
    mode: Literal["all", "specific"]
    data: list[EntitySimilarity | EntityPairSimilarity]

    @classmethod
    def from_payload(cls, payload: list[EntitySimilarity | EntityPairSimilarity]) -> "EntitySimilarityResponse":
        if not payload:
            return cls(mode="all", data=[])

        first_item = payload[0]

        if isinstance(first_item, EntitySimilarity):
            return cls(mode="specific", data=payload)

        elif isinstance(first_item, EntityPairSimilarity):
            return cls(mode="all", data=payload)

        raise ValueError("Tipo de payload desconhecido")


class EntityMergeResponse(BaseModel):
    documents_updated: int
    entities_deleted: int

    model_config = ConfigDict(from_attributes=True)


class EntityRelevance(BaseModel):
    entity_id: int
    name: str
    entity_type: str
    total_usage: int

    model_config = ConfigDict(from_attributes=True)


class EntityRelevanceResponse(BaseModel):
    data: list[EntityRelevance]


class CrossDomainConflict(BaseModel):
    tag_id: int
    tag_name: str
    entity_id: int
    entity_name: str
    entity_type: str
    similarity: float


class ConflictResolutionData(BaseModel):
    winner: Literal["TAG", "ENTITY"]
    documents_transferred: int

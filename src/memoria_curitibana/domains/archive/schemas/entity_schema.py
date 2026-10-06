from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from memoria_curitibana.domains.archive.schemas.types import EntityName

# Who recorded a NER exclusion: a human curator or the LLM conflict judge.
NerExclusionSource = Literal["JUDGE", "HUMAN"]


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


class NerExclusion(BaseModel):
    """A durable decision that a spelling belongs to the TAG axis, not to NER."""

    term: str
    reason: str | None
    source: NerExclusionSource
    tag_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ROUTE RESPONSES (the shape the API answers with)
# ==========================================
#
# These routes returned a plain ``dict``, which the generated client cannot see: the curator front
# would read them through a cast, and a renamed key would reach the screen as ``undefined``. The
# keys are the ones those routes already sent.


class NerExclusionBanResponse(BaseModel):
    """Terms banned from NER, and how many already-extracted entities the ban purged."""

    message: str
    entities_deleted: int


class NerExclusionRemovalResponse(BaseModel):
    """The ban was lifted: the extractor will consider those spellings again."""

    message: str
    removed: int


class OrphanEntityPurgeResponse(BaseModel):
    """Delete of the entities no description carries."""

    message: str
    entities_deleted: int


class EntityReclassifyResponse(BaseModel):
    """
    The new type, and the promise that matters: reclassifying writes the anchoring synonym.

    It is not a label change. The synonym makes the extractor obey the decision on every
    future run, which is why the screen has to say so.
    """

    message: str
    new_type: Literal["ORG", "PER", "LOC"]


class EntityDeleteResponse(BaseModel):
    """One entity removed from the vocabulary."""

    message: str

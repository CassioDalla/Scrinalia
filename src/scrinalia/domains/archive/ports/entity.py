from collections.abc import Sequence
from typing import Literal, Protocol

from scrinalia.core.author import Author
from scrinalia.domains.archive.schemas.command_schema import EntityLinkCommand, SynonymCommand
from scrinalia.domains.archive.schemas.entity_schema import (
    ArchiveEntityDTO,
    ConflictResolutionData,
    ConflictResolutionLogEntry,
    ConflictResolutionPlan,
    CrossDomainConflict,
    CrossDomainConflictPage,
    EntityIdentity,
    EntityPairSimilarity,
    EntityRelevance,
    EntitySimilarity,
    JudgedConflictPage,
    NerExclusion,
    NerExclusionSource,
    NerSynonymRule,
)


class EntityRepositoryPort(Protocol):
    """
    Output port for the named entities (NER) dimension.

    Read methods that feed analytics/UI return DTOs. Write methods still operate
    on ORM entities/primitives; returning domain DTOs for the write side is a known
    debt (see `.analysis/adr-arquitetura-alvo.md`).
    """

    # --- Read (analytics / curation) ---
    def find_similar(
        self, target_name: str, entity_type: Literal["ORG", "PER", "LOC"] | None = None, threshold: float = 0.5
    ) -> Sequence[EntitySimilarity]:
        raise NotImplementedError

    def find_all_similar_pairs(self, threshold: float = 0.65) -> Sequence[EntityPairSimilarity]:
        raise NotImplementedError

    def get_cross_domain_conflicts(self, threshold: float) -> Sequence[CrossDomainConflict]:
        raise NotImplementedError

    def page_cross_domain_conflicts(
        self,
        threshold: float = 0.85,
        pair_kind: Literal["all", "exact_name", "near_duplicate"] = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> CrossDomainConflictPage:
        raise NotImplementedError

    def list_judged_conflicts(self, limit: int = 50, offset: int = 0) -> JudgedConflictPage:
        raise NotImplementedError

    def plan_conflict_resolution(self, tag_id: int, entity_id: int, similarity: float = 0.0) -> ConflictResolutionPlan:
        raise NotImplementedError

    def list_conflict_resolutions(
        self, include_undone: bool = True, limit: int = 50, offset: int = 0
    ) -> tuple[list[ConflictResolutionLogEntry], int]:
        raise NotImplementedError

    def undo_conflict_resolution(
        self, resolution_id: int, undone_by: Author | None = None
    ) -> ConflictResolutionLogEntry:
        raise NotImplementedError

    def get_relevance_count(
        self, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> Sequence[EntityRelevance]:
        raise NotImplementedError

    def search_entities(self, term: str, limit: int) -> Sequence[EntityRelevance]:
        raise NotImplementedError

    def get_ner_synonyms_rules(self) -> list[NerSynonymRule]:
        raise NotImplementedError

    def get_ner_exclusion_terms(self) -> set[str]:
        raise NotImplementedError

    def list_ner_exclusions(self) -> Sequence[NerExclusion]:
        raise NotImplementedError

    # --- Write ---
    def get_or_create_entities(self, entities_list: list[ArchiveEntityDTO]) -> list[int]:
        raise NotImplementedError

    def get_by_id(self, entity_id: int) -> EntityIdentity | None:
        raise NotImplementedError

    def get_by_ids(self, entity_ids: list[int]) -> Sequence[EntityIdentity]:
        raise NotImplementedError

    def get_document_ids_by_entities(self, entity_ids: list[int]) -> Sequence[str]:
        raise NotImplementedError

    def link_documents_to_entity(self, doc_ids: set[str], target_entity_id: int) -> None:
        raise NotImplementedError

    def link_entities_to_document(self, description_id: str, entity_ids: list[int]) -> None:
        raise NotImplementedError

    def bulk_link_entities(self, links: Sequence[EntityLinkCommand]) -> None:
        raise NotImplementedError

    def create_synonyms(self, synonyms_data: list[SynonymCommand]) -> None:
        raise NotImplementedError

    def repoint_synonyms(self, from_entity_ids: list[int], to_entity_id: int) -> int:
        raise NotImplementedError

    def delete_entities(self, entity_ids: list[int]) -> int:
        raise NotImplementedError

    def update_entity_type(self, entity_id: int, new_type: str) -> None:
        raise NotImplementedError

    def update_entity_name(self, entity_id: int, new_name: str) -> None:
        raise NotImplementedError

    def delete_entities_by_names(self, names: list[str]) -> int:
        raise NotImplementedError

    def purge_orphan_entities(self) -> int:
        raise NotImplementedError

    def add_ner_exclusions(
        self,
        terms: Sequence[str],
        *,
        source: NerExclusionSource = "HUMAN",
        reason: str | None = None,
        tag_id: int | None = None,
    ) -> int:
        raise NotImplementedError

    def remove_ner_exclusions(self, terms: Sequence[str]) -> int:
        raise NotImplementedError

    def apply_conflict_resolution(
        self,
        plan: ConflictResolutionPlan,
        winner: Literal["TAG", "ENTITY"],
        source: NerExclusionSource = "HUMAN",
        decided_by: Author | None = None,
        note: str | None = None,
    ) -> ConflictResolutionData:
        raise NotImplementedError

    def resolve_cross_domain_conflict(
        self,
        winner: Literal["TAG", "ENTITY"],
        tag_id: int,
        entity_id: int,
        source: NerExclusionSource = "HUMAN",
    ) -> int:
        raise NotImplementedError

from collections.abc import Sequence
from typing import Literal, cast

from memoria_curitibana.domains.archive.domain.normalization import normalize_entity
from memoria_curitibana.domains.archive.exceptions import InvalidParam
from memoria_curitibana.domains.archive.ports.entity import EntityRepositoryPort
from memoria_curitibana.domains.archive.schemas.command_schema import (
    MergeEntityCommand,
    ResolveConflictCommand,
    SynonymCommand,
)
from memoria_curitibana.domains.archive.schemas.entity_schema import (
    ConflictResolutionData,
    CrossDomainConflict,
    EntityMergeResponse,
    EntityPairSimilarity,
    EntityRelevance,
    EntitySimilarity,
    NerExclusion,
)


class EntityService:
    """
    Domain service responsible for auditing, sanitizing and unifying
    named entities (People, Organizations, Locations) in the collection.
    """

    def __init__(self, repo: EntityRepositoryPort):
        self.repo = repo

    def find_similar(
        self, target_name: str, entity_type: Literal["ORG", "PER", "LOC"] | None = None, threshold: float = 0.5
    ) -> Sequence[EntitySimilarity]:
        if not target_name:
            raise InvalidParam("O parâmetro 'target_name' é obrigatório.")

        # Business rule: the search must always be sent in lowercase
        target_lower = target_name.strip().lower()

        return list(self.repo.find_similar(target_lower, entity_type, threshold))

    def find_all_similar_entity_pairs(self, threshold: float = 0.65) -> Sequence[EntityPairSimilarity]:
        return list(self.repo.find_all_similar_pairs(threshold))

    def merge(self, command: MergeEntityCommand) -> EntityMergeResponse:
        """
        Orchestrates the merging of entities applying business rules and sanitization.
        Allows renaming the canonical entity
        """
        canonical_id = command.canonical_id
        ids_to_merge = command.ids_to_merge
        new_name = command.new_name

        # Rule 1: Protection against self-merge
        real_ids = [id_ for id_ in ids_to_merge if id_ != canonical_id]

        # If there is no merge and no rename, ignore.
        if not real_ids and not new_name:
            return EntityMergeResponse(documents_updated=0, entities_deleted=0)

        # Rule 2: Validates that the canonical exists to inherit the typing
        canonical = self.repo.get_by_id(canonical_id)
        if not canonical:
            raise InvalidParam(f"Entidade canônica com ID {canonical_id} não encontrada.")

        # Rule 3: Data sanitization (Names for synonyms must be lowercase)
        dead_entities = self.repo.get_by_ids(real_ids) if real_ids else []
        synonym_names = [normalize_entity(e.name) for e in dead_entities]

        # Coordination 0: Renaming the Canonical Entity
        if new_name and new_name.strip() and normalize_entity(new_name) != normalize_entity(canonical.name):
            old_name = canonical.name
            # Adds the old name as a synonym so as not to break future searches
            synonym_names.append(normalize_entity(old_name))
            self.repo.update_entity_name(canonical_id, new_name.strip())

        # Coordination 1: Transfer documents
        unique_docs = set()
        if real_ids:
            raw_docs = self.repo.get_document_ids_by_entities(real_ids)
            unique_docs = set(raw_docs)
            if unique_docs:
                self.repo.link_documents_to_entity(unique_docs, canonical_id)

        # Coordination 2: Save synonyms (both of the dead entities and the old name)
        if synonym_names:
            synonyms_data = [
                SynonymCommand(
                    synonym_name=name,
                    category=cast("Literal['ORG', 'PER', 'LOC']", canonical.entity_type),
                    canonical_tag_id=None,
                    canonical_entity_id=canonical_id,
                )
                for name in synonym_names
            ]
            self.repo.create_synonyms(synonyms_data)

        # Coordination 3: Delete old entities
        deleted_rows = 0
        if real_ids:
            deleted_rows = self.repo.delete_entities(real_ids)

        return EntityMergeResponse(documents_updated=len(unique_docs), entities_deleted=deleted_rows)

    def get_entity_relevance_count(
        self, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> Sequence[EntityRelevance]:
        """
        Counts the relevance of entities, optionally filtering by type.
        Maps the repository results to the pure Domain DTO.
        """
        return list(self.repo.get_relevance_count(entity_type, limit))

    def purge_orphan_entities(self) -> int:
        """
        Scans and deletes entities that became orphans (without linked documents)
        after human curations or document deletions in the system.
        """
        return self.repo.purge_orphan_entities()

    def reclassify_entity(self, entity_id: int, new_type: Literal["ORG", "PER", "LOC"]) -> None:
        """
        Corrects the classification of an entity and creates an anchor (synonym)
        to prevent future false positives from the NER Worker.
        """
        canonical = self.repo.get_by_id(entity_id)
        if not canonical:
            raise InvalidParam(f"Entidade canônica com ID {entity_id} não encontrada.")

        if canonical.entity_type == new_type:
            raise InvalidParam(f"A entidade '{canonical.name}' já está classificada como {new_type}.")

        self.repo.update_entity_type(entity_id, new_type)

        # 2. Generates the anchoring synonym (in lowercase, as defined in the business rules)
        synonym_data = [
            SynonymCommand(
                synonym_name=canonical.name,
                category=new_type,
                canonical_tag_id=None,
                canonical_entity_id=entity_id,
            )
        ]

        self.repo.create_synonyms(synonym_data)

    def purge_entity_stopwords(self, words: list[str]) -> int:
        """
        Adds terms to the NER extraction blacklist and scans the database
        to purge false entities that may already have been created.
        """
        if not words:
            return 0

        # 1. Saves to the blacklist (Worker will no longer extract)
        self.repo.save_entity_stopwords(words)

        # 2. Purges the past (Cleans the current base)
        deleted_rows = self.repo.delete_entities_by_names(words)

        return deleted_rows

    def delete_entity(self, entity_id: int) -> None:
        """Surgically deletes an isolated entity from the database."""
        entity = self.repo.get_by_id(entity_id)
        if not entity:
            raise InvalidParam(f"Entidade com ID {entity_id} não encontrada para exclusão.")

        self.repo.delete_entities([entity_id])

    def exclude_terms_from_ner(
        self,
        words: list[str],
        *,
        reason: str | None = None,
        tag_id: int | None = None,
        source: Literal["JUDGE", "HUMAN"] = "HUMAN",
    ) -> int:
        """
        Records the durable decision "this term is a subject, not a named entity".

        This is the negative counterpart of ``reclassify_entity``: instead of teaching
        the NER a different label, it keeps the term out of the extraction for good
        and purges the entities already created from it.

        Args:
            words: Raw spellings to exclude. Normalized (lowercase) before storage.
            reason: Free text explaining the decision, kept for the curator.
            tag_id: The tag that justifies the exclusion, when it came from a clash.
            source: ``JUDGE`` for the LLM conflict worker, ``HUMAN`` for the curator.

        Returns:
            int: How many existing entities were deleted from the collection.
        """
        clean_words = [normalize_entity(word) for word in words if word.strip()]
        if not clean_words:
            return 0

        self.repo.add_ner_exclusions(clean_words, source=source, reason=reason, tag_id=tag_id)

        # The exclusion also applies to the past: entities built from that spelling are
        # purged. Links are dropped by cascade; the caller decides whether the documents
        # should receive the winning tag (``resolve_cross_domain_conflict`` does it).
        return self.repo.delete_entities_by_names(clean_words)

    def list_ner_exclusions(self) -> Sequence[NerExclusion]:
        """Lists every term currently excluded from NER extraction."""
        return self.repo.list_ner_exclusions()

    def remove_ner_exclusions(self, words: list[str]) -> int:
        """Undoes an exclusion, re-opening the term for the NER engine."""
        clean_words = [normalize_entity(word) for word in words if word.strip()]
        if not clean_words:
            return 0

        return self.repo.remove_ner_exclusions(clean_words)

    def find_cross_domain_conflicts(self, threshold: float = 0.85) -> Sequence[CrossDomainConflict]:
        """Scans the database looking for Tags and Entities that have the same name or very close spelling."""
        return list(self.repo.get_cross_domain_conflicts(threshold))

    def resolve_cross_domain_conflict(
        self, command: ResolveConflictCommand, source: Literal["JUDGE", "HUMAN"] = "HUMAN"
    ) -> ConflictResolutionData:
        """
        Resolves the conflict by transferring the relationships to the winner and purging the loser.

        Args:
            command: Winner and the pair being resolved.
            source: Who decided, forwarded to the NER exclusion catalog when the TAG wins.
        """
        transferred_docs = self.repo.resolve_cross_domain_conflict(
            command.winner, command.tag_id, command.entity_id, source=source
        )

        return ConflictResolutionData(winner=command.winner, documents_transferred=transferred_docs)

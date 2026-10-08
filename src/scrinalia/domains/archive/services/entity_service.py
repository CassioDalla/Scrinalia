from collections.abc import Sequence
from typing import Literal, cast

from scrinalia.core.author import Author
from scrinalia.domains.archive.domain.normalization import normalize_entity
from scrinalia.domains.archive.exceptions import InvalidParam
from scrinalia.domains.archive.ports.entity import EntityRepositoryPort
from scrinalia.domains.archive.schemas.command_schema import (
    MergeEntityCommand,
    ResolveConflictCommand,
    SynonymCommand,
)
from scrinalia.domains.archive.schemas.entity_schema import (
    ConflictResolutionData,
    ConflictResolutionLogEntry,
    ConflictResolutionPlan,
    CrossDomainConflict,
    CrossDomainConflictPage,
    EntityMergeResponse,
    EntityPairSimilarity,
    EntityRelevance,
    EntitySimilarity,
    JudgedConflictPage,
    NerExclusion,
)

#: Character floor of an entity search, mirroring the tags': one letter matches an arbitrary slice
#: of 3.808 names, and the box is for choosing one of them.
MIN_ENTITY_SEARCH_TERM = 2


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

        # Coordination 2: Save synonyms (both of the dead entities and the old name). The
        # spellings already absorbed by the dead entities are moved to the canonical BEFORE
        # the delete below: the FK is ON DELETE CASCADE, so deleting first would destroy the
        # earlier curation and the next extraction would recreate the term.
        self.repo.repoint_synonyms(real_ids, canonical_id)

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

    def search_entities(self, term: str, limit: int = 20) -> Sequence[EntityRelevance]:
        """
        Entities matching what the curator is typing, for the type-ahead of the dossier.

        The floor of two characters is the same one the tags use and for the same reason: the
        collection carries 3.808 entities, and one letter would return an arbitrary slice of them.
        """
        if len(term.strip()) < MIN_ENTITY_SEARCH_TERM:
            return []
        return list(self.repo.search_entities(term, limit))

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

    def page_cross_domain_conflicts(
        self,
        threshold: float = 0.85,
        pair_kind: Literal["all", "exact_name", "near_duplicate"] = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> CrossDomainConflictPage:
        """
        One page of the live collisions, annotated with the judge's verdict and the ledger's write.

        The list is the *pending* work, and it is only usable because of ``scope``: on the real
        collection the trigram join returns 5 408 pairs, of which 5 050 are the same spelling on both
        axes and 122 are the same word written differently. Those are two different questions, and
        the screen chooses which one to open.
        """
        if not 0 < threshold <= 1:
            raise InvalidParam("O parâmetro 'threshold' deve estar entre 0 e 1.")
        return self.repo.page_cross_domain_conflicts(
            threshold=threshold, pair_kind=pair_kind, limit=limit, offset=offset
        )

    def list_judged_conflicts(self, limit: int = 50, offset: int = 0) -> JudgedConflictPage:
        """
        The pairs the judge already evaluated, read from the review queue.

        Deliberately not the live scan: an auto-resolution deletes the losing row, so 84 of the 88
        real decisions cannot appear in a trigram join. The queue is where the judge's work survives.
        """
        return self.repo.list_judged_conflicts(limit=limit, offset=offset)

    def plan_conflict_resolution(self, tag_id: int, entity_id: int) -> ConflictResolutionPlan:
        """
        What each verdict would do, computed without writing anything.

        Both sides of the comparison are returned, because "which one wins?" is a question about the
        difference between them, and the answer has to be in front of the archivist before the click.
        """
        return self.repo.plan_conflict_resolution(tag_id, entity_id)

    def resolve_cross_domain_conflict(
        self, command: ResolveConflictCommand, source: Literal["JUDGE", "HUMAN"] = "HUMAN"
    ) -> ConflictResolutionData:
        """
        Resolves the conflict by transferring the relationships to the winner and purging the loser.

        Goes through plan + apply, so the write always leaves a ledger row and is therefore
        reversible — the judge's auto-resolution included, which used to call the raw transfer and
        left nothing behind.

        Args:
            command: Winner, the pair being resolved, who decided and why.
            source: Who decided, forwarded to the ledger and to the governance write.
        """
        plan = self.repo.plan_conflict_resolution(command.tag_id, command.entity_id)
        return self.repo.apply_conflict_resolution(
            plan,
            command.winner,
            source=source,
            decided_by=command.decided_by,
            note=command.note,
        )

    def list_conflict_resolutions(
        self, include_undone: bool = True, limit: int = 50, offset: int = 0
    ) -> tuple[list[ConflictResolutionLogEntry], int]:
        """The audit trail of the resolutions: what was written, by whom, and what was reversed."""
        return self.repo.list_conflict_resolutions(include_undone=include_undone, limit=limit, offset=offset)

    def undo_conflict_resolution(
        self, resolution_id: int, undone_by: Author | None = None
    ) -> ConflictResolutionLogEntry:
        """
        Reverses one resolution: the losing row, its links and the ban it planted.

        The second attempt is a conflict and an unknown id is a not-found, because a silent no-op
        would read as "it worked" when nothing was restored.
        """
        return self.repo.undo_conflict_resolution(resolution_id, undone_by=undone_by)

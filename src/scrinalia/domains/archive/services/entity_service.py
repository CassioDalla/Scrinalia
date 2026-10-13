from collections.abc import Sequence
from typing import Literal

from scrinalia.core.author import Author
from scrinalia.core.logger import logger
from scrinalia.domains.archive.domain.normalization import normalize_entity
from scrinalia.domains.archive.exceptions import EntityNotFoundError, InvalidParam
from scrinalia.domains.archive.ports.entity import EntityRepositoryPort
from scrinalia.domains.archive.schemas.command_schema import (
    MergeEntityCommand,
    MergeEntityPreviewCommand,
    ResolveConflictBatchCommand,
    ResolveConflictCommand,
    SynonymCommand,
)
from scrinalia.domains.archive.schemas.entity_schema import (
    ConflictBatchResult,
    ConflictPairKind,
    ConflictResolutionData,
    ConflictResolutionLogEntry,
    ConflictResolutionPlan,
    CrossDomainConflict,
    CrossDomainConflictPage,
    EntityIdentity,
    EntityKind,
    EntityMergeLogEntryDTO,
    EntityMergeLogListResponse,
    EntityMergePreviewResponse,
    EntityMergeResponse,
    EntityPairSimilarity,
    EntityRelevance,
    EntitySimilarity,
    JudgedConflictPage,
    NerExclusion,
    NerPurgeEntity,
    NerPurgeLogEntryDTO,
    NerPurgeLogListResponse,
    NerPurgePreview,
    NerPurgeResult,
)

#: Character floor of an entity search, mirroring the tags': one letter matches an arbitrary slice
#: of 3.808 names, and the box is for choosing one of them.
MIN_ENTITY_SEARCH_TERM = 2

#: How many pairs one batch request may write. The tag merge batch caps its clusters at 200 for the
#: same reason: every unit is individually undoable, but a single click that writes thousands of
#: ledger rows is a click nobody reviewed.
MAX_CONFLICT_BATCH_PAIRS = 200


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
        Unifies entities into the canonical one, optionally renaming it.

        Plan + apply, exactly like the tag merge: the same planner computes the impact and the
        writer executes it, so the dry run cannot promise a different number from the write. The
        write is logged per absorbed entity in the ledger, which is what makes it reversible.
        """
        canonical_id = command.canonical_id
        # Protection against self-merge: the canonical is not absorbed into itself.
        real_ids = [id_ for id_ in command.ids_to_merge if id_ != canonical_id]

        # If there is no merge and no rename, ignore.
        if not real_ids and not (command.new_name and command.new_name.strip()):
            return EntityMergeResponse(documents_updated=0, entities_deleted=0)

        plan = self.repo.plan_entity_merge(canonical_id, real_ids, command.new_name)
        return self.repo.apply_entity_merge(plan, changed_by=command.changed_by, note=command.note)

    def preview_merge(self, command: MergeEntityPreviewCommand) -> EntityMergePreviewResponse:
        """
        Dry-run of a merge: what changes, what is lost and why the archivist should look twice.

        Read-only by construction (it only calls ``plan_entity_merge``), which is the point: the
        archivist decides with a number and a warning in hand, never on the hope that the cluster
        is harmless.
        """
        real_ids = [id_ for id_ in command.ids_to_merge if id_ != command.canonical_id]
        plan = self.repo.plan_entity_merge(command.canonical_id, real_ids, command.new_name)
        return EntityMergePreviewResponse(
            canonical_id=plan.canonical_id,
            canonical_name=plan.canonical_name,
            documents_updated=plan.documents_updated,
            links_rewritten=plan.links_rewritten,
            entities_deleted=plan.impacted,
            synonyms_created=plan.synonym_names,
            synonyms_repointed=plan.repointed_synonyms,
            renamed_from=plan.rename_from,
            renamed_to=plan.rename_to,
            review_flags=plan.review_flags,
        )

    def rename_entity(
        self,
        entity_id: int,
        new_name: str,
        *,
        keep_old_synonym: bool = True,
        changed_by: Author | None = None,
        note: str | None = None,
    ) -> tuple[EntityIdentity, int]:
        """
        Renames one entity, leaving the ledger row that makes it reversible.

        One definition of "rename a name" (the repository method the merge also calls), so the
        single-entity rename and the merge's optional rename cannot drift apart. An unknown id is a
        business error, never a silent no-op.

        The ledger row is written **here** and not in the repository, because the merge already logged
        its own rename in the row per absorbed entity: a writer inside ``rename_entity`` would put two
        rows under one decision. Returns the entity as it now reads and the ledger id of the undo.
        """
        if not new_name.strip():
            raise InvalidParam("O novo nome da entidade não pode ser vazio.")

        record = self.repo.rename_entity(entity_id, new_name, keep_old_synonym=keep_old_synonym)
        if record is None:
            raise EntityNotFoundError(f"Entidade com ID {entity_id} não encontrada.")

        merge_id = self.repo.write_entity_rename_log(record, changed_by=changed_by, note=note)

        renamed = self.repo.get_by_id(entity_id)
        if renamed is None:
            raise EntityNotFoundError(f"Entidade com ID {entity_id} não encontrada após o rename.")
        return renamed, merge_id

    def list_merge_log(
        self,
        canonical_id: int | None = None,
        changed_by_name: str | None = None,
        include_undone: bool = True,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> EntityMergeLogListResponse:
        """One page of the merge ledger, with the total matching the same filters."""
        total = self.repo.count_entity_merge_log(
            canonical_id=canonical_id, changed_by_name=changed_by_name, include_undone=include_undone, term=term
        )
        items = self.repo.list_entity_merge_log(
            canonical_id=canonical_id,
            changed_by_name=changed_by_name,
            include_undone=include_undone,
            term=term,
            limit=limit,
            offset=offset,
        )
        return EntityMergeLogListResponse(total=total, limit=limit, offset=offset, items=items)

    def undo_merge(self, merge_id: int, undone_by: Author | None = None) -> EntityMergeLogEntryDTO:
        """
        Reverses one merge from the ledger, restoring the entity, its links and the canonical name.

        The second attempt is a conflict and an unknown id is a not-found, because a silent no-op
        would read as "it worked" when nothing was restored.
        """
        entry = self.repo.undo_entity_merge(merge_id, undone_by=undone_by)
        logger.info(f"↩️ Mesclagem de entidade {merge_id} desfeita: '{entry.absorbed_name}' restaurada.")
        return entry

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

        The negative counterpart of ``reclassify_entity``: instead of teaching the NER a different
        label, it keeps the term out of the extraction for good. It **deletes nothing** — the
        entities already extracted from the spelling are removed by :meth:`purge_ner_terms`, a
        separate act with its own preview and ledger, because a reversible toggle must not carry an
        irreversible loss (#94).

        Args:
            words: Raw spellings to exclude. Normalized (lowercase) before storage.
            reason: Free text explaining the decision, kept for the curator.
            tag_id: The tag that justifies the exclusion, when it came from a clash.
            source: ``JUDGE`` for the LLM conflict worker, ``HUMAN`` for the curator.

        Returns:
            int: How many exclusions were actually inserted (the ban is idempotent).
        """
        clean_words = [normalize_entity(word) for word in words if word.strip()]
        if not clean_words:
            return 0

        return self.repo.add_ner_exclusions(clean_words, source=source, reason=reason, tag_id=tag_id)

    def list_ner_exclusions(self) -> Sequence[NerExclusion]:
        """Lists every term currently excluded from NER extraction."""
        return self.repo.list_ner_exclusions()

    def preview_ner_purge(self) -> NerPurgePreview:
        """
        The dry run of the purge: the entities that would die, and the ledger that can bring them back.

        Computed from the same plan :meth:`purge_ner_terms` consumes, so the list the archivist
        approves is the list the write deletes.
        """
        plan = self.repo.plan_ner_purge()
        return NerPurgePreview(
            excluded_terms=plan.excluded_terms,
            entities=[
                NerPurgeEntity(
                    entity_id=item.entity_id,
                    name=item.name,
                    entity_type=item.entity_type,
                    excluded_term=item.excluded_term,
                    document_count=len(item.document_ids),
                    synonym_names=item.synonym_names,
                )
                for item in plan.items
            ],
            total_entities=plan.total_entities,
            total_documents=plan.total_documents,
            reversible=True,
        )

    def purge_ner_terms(self, changed_by: Author | None = None) -> NerPurgeResult:
        """
        Deletes every entity whose spelling is a banned term, after logging each one in the ledger.

        The plan is recomputed here from ``domain_ner_exclusions``, which is the same computation
        the preview ran: the screen applies the list it showed.
        """
        plan = self.repo.plan_ner_purge()
        if not plan.items:
            return NerPurgeResult()

        return self.repo.apply_ner_purge(plan, changed_by=changed_by)

    def undo_ner_purge(self, purge_id: int, undone_by: Author | None = None) -> NerPurgeLogEntryDTO:
        """
        Reverses one purge: the entity, its links and its spellings come back.

        The veto stays — the term is still excluded, and the next purge lists the restored entity
        again. An unknown id is a not-found and a second undo is a conflict, because a silent no-op
        would read as "it worked" when nothing was restored.
        """
        return self.repo.undo_ner_purge(purge_id, undone_by=undone_by)

    def list_ner_purge_log(
        self, include_undone: bool = True, term: str | None = None, limit: int = 50, offset: int = 0
    ) -> NerPurgeLogListResponse:
        """The audit trail of the NER purges: what died, by whom, and what was restored."""
        return self.repo.list_ner_purge_log(include_undone=include_undone, term=term, limit=limit, offset=offset)

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
        pair_kind: ConflictPairKind = "all",
        entity_type: EntityKind | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CrossDomainConflictPage:
        """
        One page of the live collisions, annotated with the judge's verdict and the ledger's write.

        The list is the *pending* work, and it is only usable because of ``pair_kind``: on the real
        collection the trigram join returns thousands of pairs, most of them the same spelling on both
        axes and a minority the same word written differently. Those are two different questions, and
        the screen chooses which one to open. ``entity_type`` narrows the structural population to a
        category — the same selection the batch writes.
        """
        if not 0 < threshold <= 1:
            raise InvalidParam("O parâmetro 'threshold' deve estar entre 0 e 1.")
        return self.repo.page_cross_domain_conflicts(
            threshold=threshold, pair_kind=pair_kind, entity_type=entity_type, limit=limit, offset=offset
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

    def resolve_conflict_batch(self, command: ResolveConflictBatchCommand) -> ConflictBatchResult:
        """
        Applies one categorical verdict — "a street is an entity" — to a whole selection of pairs.

        The batch is the unit of the *decision*, never of the write: the repository still resolves
        pair by pair, each in its own savepoint and with its own ledger row, so every pair keeps an
        independent undo and a pair that cannot be resolved is reported instead of aborting the rest.
        The bounds are validated here so the API route stays a thin translation of the command.
        """
        if not 0 < command.threshold <= 1:
            raise InvalidParam("O parâmetro 'threshold' deve estar entre 0 e 1.")
        if not 1 <= command.limit <= MAX_CONFLICT_BATCH_PAIRS:
            raise InvalidParam(f"O lote aceita entre 1 e {MAX_CONFLICT_BATCH_PAIRS} pares por requisição.")

        return self.repo.resolve_conflict_batch(
            winner=command.winner,
            pair_kind=command.pair_kind,
            entity_type=command.entity_type,
            threshold=command.threshold,
            limit=command.limit,
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

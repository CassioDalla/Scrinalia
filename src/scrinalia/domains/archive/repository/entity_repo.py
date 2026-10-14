from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, delete, desc, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from scrinalia.core.author import Author, assign_author, author_columns
from scrinalia.domains.archive.domain.entity_merge import (
    KIND_MERGE,
    KIND_RENAME,
    REVIEW_MEMBER_IS_SYNONYM,
    REVIEW_MEMBER_WITH_DIGITS,
    REVIEW_MIXED_TYPES,
    REVIEW_ORPHAN_MEMBER,
    EntityRenameRecord,
)
from scrinalia.domains.archive.domain.normalization import (
    LIKE_ESCAPE,
    escape_like,
    normalize_entity,
    normalize_stopword,
)
from scrinalia.domains.archive.domain.tag_merge import has_digits
from scrinalia.domains.archive.exceptions import (
    ConflictResolutionAlreadyUndoneError,
    ConflictResolutionNotFoundError,
    DuplicateEntityNameError,
    InvalidMergeError,
    InvalidParam,
    MergeAlreadyUndoneError,
    MergeLogNotFoundError,
    NerPurgeAlreadyUndoneError,
    NerPurgeLogNotFoundError,
    UnresolvableConflictError,
)
from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveConflictResolutionLog,
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveEntityMergeLog,
    ArchiveNerPurgeLog,
    ArchiveReviewStatus,
    ArchiveTag,
    DomainNerExclusion,
    DomainStopwords,
    DomainSynonyms,
    StopwordsScope,
)
from scrinalia.domains.archive.repository.synonym_upsert import upsert_synonyms
from scrinalia.domains.archive.schemas.command_schema import EntityLinkCommand, SynonymCommand
from scrinalia.domains.archive.schemas.entity_schema import (
    ArchiveEntityDTO,
    ConflictBanKind,
    ConflictBatchEntry,
    ConflictBatchRemaining,
    ConflictBatchResult,
    ConflictBatchSkip,
    ConflictDecider,
    ConflictPairKind,
    ConflictResolutionData,
    ConflictResolutionLogEntry,
    ConflictResolutionPlan,
    ConflictWinner,
    CrossDomainConflict,
    CrossDomainConflictPage,
    EntityIdentity,
    EntityKind,
    EntityMergeImpact,
    EntityMergeLogEntryDTO,
    EntityMergePlan,
    EntityMergeResponse,
    EntityPairSimilarity,
    EntityRelevance,
    EntitySimilarity,
    JudgedConflict,
    JudgedConflictPage,
    NerExclusion,
    NerExclusionSource,
    NerPurgeItem,
    NerPurgeLogEntryDTO,
    NerPurgeLogListResponse,
    NerPurgePlan,
    NerPurgeResult,
    NerSynonymRule,
)

#: The three categories a named-entity synonym can live in. Declared once because the spelling
#: dictionary is looked up by category, and a merge writes and restores the canonical's own.
ENTITY_SYNONYM_CATEGORIES = ("ORG", "PER", "LOC")


def _jsonable(value: Any) -> Any:
    """Turns a column value into something JSONB can hold (dates become ISO strings)."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class EntityRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, entity_id: int) -> EntityIdentity | None:
        obj = self.db.scalar(select(ArchiveEntity).where(ArchiveEntity.entity_id == entity_id))
        return EntityIdentity.model_validate(obj) if obj else None

    def get_by_ids(self, entity_ids: list[int]) -> Sequence[EntityIdentity]:
        if not entity_ids:
            return []
        objs = self.db.scalars(select(ArchiveEntity).where(ArchiveEntity.entity_id.in_(entity_ids))).all()
        return [EntityIdentity.model_validate(obj) for obj in objs]

    def find_similar(
        self, target_name: str, entity_type: Literal["ORG", "PER", "LOC"] | None = None, threshold: float = 0.5
    ) -> Sequence[EntitySimilarity]:
        """
        Searches for entities with typos or high similarity using the pg_trgm extension.
        Also returns the 'entity_type' to help the user decide whether the merge makes sense.
        """

        if not target_name:
            raise InvalidParam("O parametro 'target_name' é obrigatório")

        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})

        target_lower = target_name.lower()
        similarity = func.similarity(ArchiveEntity.name, target_lower)

        stmt = (
            select(
                ArchiveEntity.entity_id, ArchiveEntity.name, ArchiveEntity.entity_type, similarity.label("similarity")
            )
            .where(ArchiveEntity.name.op("%")(target_lower))
            .where(func.lower(ArchiveEntity.name) != target_lower)
        )

        if entity_type:
            stmt = stmt.where(ArchiveEntity.entity_type == entity_type)

        stmt = stmt.order_by(desc("similarity")).limit(15)

        return [EntitySimilarity.model_validate(row) for row in self.db.execute(stmt).fetchall()]

    def find_all_similar_pairs(self, threshold: float = 0.65) -> Sequence[EntityPairSimilarity]:
        """
        Scans the collection and cross-references all entities with each other to find
        pairs that are very similar (potential duplications or NER errors).

        The ``%`` predicate is the only condition besides the self-join, and that **is** the
        performance strategy: it is what makes PostgreSQL walk ``idx_archive_entities_name_trgm``
        once per row instead of comparing every pair (measured: 196 ms for the whole collection at
        threshold 0.65, against 7.2 M pairs).

        There used to be an extra ``abs(length(a) - length(b)) <= 3`` here, labelled a performance
        hack. It was a **correctness** bug: length difference is not bounded by trigram similarity —
        ``Avenida Nossa Senhora Da Luz`` vs ``Av. Avenida Nossa Senhora Da Luz`` has similarity
        0.966 and a difference of 4 — and it silently discarded **419 of 647** real duplicate pairs
        (65%). Do not reintroduce a prefilter in front of ``%``: the index is already the filter.
        """
        # Configures PostgreSQL's native threshold only for this transaction.
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})

        # Creates the aliases for the Self Join
        Entity1 = aliased(ArchiveEntity)
        Entity2 = aliased(ArchiveEntity)

        # Prepares the similarity calculation
        similarity = func.similarity(Entity1.name, Entity2.name)

        stmt = (
            select(
                Entity1.entity_id.label("id_1"),
                Entity1.name.label("name_1"),
                Entity1.entity_type.label("type_1"),
                Entity2.entity_id.label("id_2"),
                Entity2.name.label("name_2"),
                Entity2.entity_type.label("type_2"),
                similarity.label("similarity"),
            )
            # The Join ensuring that only unique combinations are tested (A with B) and mirrored ones (B with A) are ignored
            .join(Entity2, Entity1.entity_id < Entity2.entity_id)
            # The GIN trigram index answers this one predicate; nothing else may narrow it.
            .where(Entity1.name.op("%")(Entity2.name))
            .order_by(desc("similarity"), Entity1.name)
        )

        return [EntityPairSimilarity.model_validate(row) for row in self.db.execute(stmt).all()]

    # =========================================================================
    # TAG x ENTITY COLLISION: the live scan, the judge's decisions, the ledger
    # =========================================================================
    #
    # Three reads and one write, and the distinction between them is the whole point of this
    # section. The live scan answers "which spellings collide *today*"; the review queue answers
    # "what did the judge decide"; the ledger answers "what was actually written, and can it be
    # reversed". Reading only the first one is what hid 84 of the 88 decisions on the real
    # collection — they were auto-resolutions whose losing row no longer exists.

    def get_cross_domain_conflicts(self, threshold: float) -> Sequence[CrossDomainConflict]:
        """
        Conflicts where a Tag name is identical or nearly identical to an Entity name.

        The join condition is the trigram operator and **nothing else**. That is not a stylistic
        preference: it is the difference between an index scan and a full cross product. Measured on
        the real collection (6 142 tags x 3 808 entities, threshold 0.85):

        * ``name % name`` alone → ``Bitmap Index Scan on idx_archive_tags_name_trgm``, **1.4 s**;
        * the same condition ``OR lower(t.name) = lower(e.name)`` → the OR turns the join into a
          ``Join Filter``, the planner materialises the inner side and the query scans all 23.4 M
          pairs: **52.9 s**, with **identical results**.

        The ``lower() = lower()`` disjunct was redundant, not a safety net: ``pg_trgm`` normalises
        case for trigram extraction, so ``similarity('Exemplo', 'exemplo') = 1`` and at **any** threshold
        in ``[0, 1]`` every pair it matched was already matched by ``%``. Do not add an OR here —
        it silently costs a factor of 37. ``testing/integration/archive/services/test_entity_service.py``
        pins the case-insensitivity this reasoning depends on.

        This is the **raw** scan, used by the judge worker, which has to see every pair. The API
        reads :meth:`page_cross_domain_conflicts`, which annotates each pair with what has already
        been decided and separates the two populations below.

        ``pair_kind`` travels on the DTO and is derived there from the score: ``EXACT_NAME`` is the
        same spelling on both axes and ``NEAR_DUPLICATE`` is the same word written differently. On
        the real collection the split is 5 050 / 122 — mixing them produced a 5 408-card queue in
        which the real work was invisible.
        """
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})

        sim_score = func.similarity(ArchiveTag.name, ArchiveEntity.name)

        stmt = (
            select(
                ArchiveTag.tag_id,
                ArchiveTag.name.label("tag_name"),
                ArchiveEntity.entity_id,
                ArchiveEntity.name.label("entity_name"),
                ArchiveEntity.entity_type,
                sim_score.label("similarity"),
            )
            .join(ArchiveEntity, ArchiveTag.name.op("%")(ArchiveEntity.name))
            # The id tie-breakers make the order **total**, which is what lets a batch slice the
            # selection without the set it writes depending on the planner's mood: ``similarity``
            # alone is full of ties (every ``EXACT_NAME`` pair scores exactly 1).
            .order_by(desc("similarity"), ArchiveTag.tag_id, ArchiveEntity.entity_id)
        )
        return [CrossDomainConflict.model_validate(dict(row._mapping)) for row in self.db.execute(stmt).all()]

    def _judge_verdicts(self) -> dict[tuple[int, int], dict[str, Any]]:
        """
        The judge's verdict per pair, keyed by ``(tag_id, entity_id)``.

        One indexed read of the review queue rather than a correlated lookup per row of the live
        scan: the queue is small by nature (88 rows on the real collection, against 5 408 live
        pairs) and ``anomaly_type`` is indexed, so the whole verdict set fits in one query.
        """
        stmt = select(
            ArchiveAIReviewQueue.context_payload,
            ArchiveAIReviewQueue.llm_decision,
            ArchiveAIReviewQueue.llm_confidence,
            ArchiveAIReviewQueue.llm_reason,
            ArchiveAIReviewQueue.status,
        ).where(ArchiveAIReviewQueue.anomaly_type == AnomalyType.CROSS_DOMAIN_COLLISION)

        verdicts: dict[tuple[int, int], dict[str, Any]] = {}
        for payload, decision, confidence, reason, status in self.db.execute(stmt).all():
            pair = (int(payload.get("tag_id", 0)), int(payload.get("entity_id", 0)))
            verdicts[pair] = {
                "judge_winner": decision,
                "judge_confidence": confidence,
                "judge_reason": reason,
                "judge_status": str(status),
            }
        return verdicts

    def _active_resolutions(self) -> dict[tuple[int, int], tuple[int, str, str]]:
        """The resolution in force per pair, keyed by ``(tag_id, entity_id)``. Undone ones are out."""
        stmt = select(
            ArchiveConflictResolutionLog.tag_id,
            ArchiveConflictResolutionLog.entity_id,
            ArchiveConflictResolutionLog.resolution_id,
            ArchiveConflictResolutionLog.winner,
            ArchiveConflictResolutionLog.source,
        ).where(ArchiveConflictResolutionLog.undone_at.is_(None))
        return {
            (int(tag_id), int(entity_id)): (int(resolution_id), str(winner), str(source))
            for tag_id, entity_id, resolution_id, winner, source in self.db.execute(stmt).all()
        }

    def _select_conflicts(
        self,
        threshold: float = 0.85,
        pair_kind: ConflictPairKind = "all",
        entity_type: EntityKind | None = None,
    ) -> list[CrossDomainConflict]:
        """
        The annotated live scan, filtered by population and category — **the** definition of "the
        selection".

        The page, the counts and the batch all read this one method, so the number the archivist sees
        and the set the batch writes cannot become two different measurements. The scan is not
        paginable in SQL (the trigram join produces and sorts the whole candidate set before a page
        means anything), so the selection is materialised in Python; ``get_cross_domain_conflicts``
        orders it by similarity with the id tie-breakers, which is what makes the order total and a
        batch slice deterministic.

        ``pair_kind`` is the lever that makes the list usable: ``exact_name`` is a structural question
        (the same spelling on both axes) and ``near_duplicate`` a spelling question. ``entity_type``
        narrows it to a category, because "a street is an entity" is a decision about a set and not
        about a pair.
        """
        verdicts = self._judge_verdicts()
        resolutions = self._active_resolutions()

        selected: list[CrossDomainConflict] = []
        for conflict in self.get_cross_domain_conflicts(threshold):
            if entity_type is not None and conflict.entity_type != entity_type:
                continue
            if pair_kind == "exact_name" and conflict.pair_kind != "EXACT_NAME":
                continue
            if pair_kind == "near_duplicate" and conflict.pair_kind != "NEAR_DUPLICATE":
                continue
            pair = (conflict.tag_id, conflict.entity_id)
            verdict = verdicts.get(pair, {})
            resolution = resolutions.get(pair)
            selected.append(
                conflict.model_copy(
                    update={
                        **verdict,
                        "resolution_id": resolution[0] if resolution else None,
                        "resolution_winner": resolution[1] if resolution else None,
                        "resolution_source": resolution[2] if resolution else None,
                    }
                )
            )
        return selected

    def page_cross_domain_conflicts(
        self,
        threshold: float = 0.85,
        pair_kind: ConflictPairKind = "all",
        entity_type: EntityKind | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CrossDomainConflictPage:
        """
        One page of the live scan, annotated with what has already been decided about each pair.

        The page is sliced after the scan, and the counts are over the **whole** filtered set rather
        than the page: the screen's "122 grafias diferentes / 5 050 nomes idênticos" cannot come from
        a page.

        The parameter is not called ``scope`` because Litestar reserves that name for the ASGI scope:
        a handler parameter called ``scope`` silently receives the raw request instead of the query
        string. The stopwords route was bitten by the same trap and renamed its key to ``axis``.
        """
        filtered = self._select_conflicts(threshold, pair_kind, entity_type)

        return CrossDomainConflictPage(
            total=len(filtered),
            limit=limit,
            offset=offset,
            items=filtered[offset : offset + limit],
            exact_name_count=sum(1 for row in filtered if row.pair_kind == "EXACT_NAME"),
            near_duplicate_count=sum(1 for row in filtered if row.pair_kind == "NEAR_DUPLICATE"),
            judged_count=sum(1 for row in filtered if row.judge_winner is not None or row.resolution_id is not None),
        )

    def resolve_conflict_batch(
        self,
        winner: ConflictWinner,
        pair_kind: ConflictPairKind = "exact_name",
        entity_type: EntityKind | None = None,
        threshold: float = 0.85,
        limit: int = 50,
        source: ConflictDecider = "HUMAN",
        decided_by: Author | None = None,
        note: str | None = None,
    ) -> ConflictBatchResult:
        """
        Applies one verdict to a whole selection, one ledger row — and one undo — per pair.

        The unit of the write is still the **pair**: each one is planned by
        ``plan_conflict_resolution`` and written by ``apply_conflict_resolution`` inside its own
        SAVEPOINT, so a pair that fails does not roll back the ones that succeeded and the request
        still ends in the single commit the unit of work owns.

        The selection is read **once**, before the first write. A resolution deletes the losing row,
        so a later pair whose loser an earlier one already removed can no longer be planned; it is
        reported in ``skipped`` with the reason — finished work, not a failure. Counting it as a
        failure is what turned a clean batch of merges into twenty red lines once already.

        ``remaining`` is recomputed through ``_select_conflicts`` with the same filters, so "before"
        and "after" are the same measurement taken twice.
        """
        selected = self._select_conflicts(threshold, pair_kind, entity_type)[:limit]
        # One read of the queue and one of the ledger for the whole batch, handed to the shared
        # planner: without this, planning N pairs reads the review queue and the ledger N times, and
        # the ledger grows with every resolution ever written.
        verdicts = self._judge_verdicts()
        resolutions = self._active_resolutions()

        applied: list[ConflictBatchEntry] = []
        skipped: list[ConflictBatchSkip] = []
        failed: list[ConflictBatchSkip] = []

        for conflict in selected:
            plan = self.plan_conflict_resolution(
                conflict.tag_id,
                conflict.entity_id,
                conflict.similarity,
                verdicts=verdicts,
                resolutions=resolutions,
            )
            if not plan.resolvable:
                skipped.append(
                    ConflictBatchSkip(
                        tag_id=conflict.tag_id,
                        entity_id=conflict.entity_id,
                        tag_name=conflict.tag_name,
                        entity_name=conflict.entity_name,
                        reason=plan.blocker or "Este par não pode mais ser resolvido.",
                    )
                )
                continue

            try:
                with self.db.begin_nested():
                    data = self.apply_conflict_resolution(plan, winner, source=source, decided_by=decided_by, note=note)
            except Exception as exc:
                failed.append(
                    ConflictBatchSkip(
                        tag_id=conflict.tag_id,
                        entity_id=conflict.entity_id,
                        tag_name=conflict.tag_name,
                        entity_name=conflict.entity_name,
                        reason=str(exc),
                    )
                )
            else:
                applied.append(
                    ConflictBatchEntry(
                        resolution_id=data.resolution_id or 0,
                        tag_id=conflict.tag_id,
                        tag_name=conflict.tag_name,
                        entity_id=conflict.entity_id,
                        entity_name=conflict.entity_name,
                        documents_transferred=data.documents_transferred,
                    )
                )

        remaining = self._select_conflicts(threshold, pair_kind, entity_type)
        return ConflictBatchResult(
            winner=winner,
            pair_kind=pair_kind,
            entity_type=entity_type,
            applied=applied,
            skipped=skipped,
            failed=failed,
            remaining=ConflictBatchRemaining(
                total=len(remaining),
                exact_name_count=sum(1 for row in remaining if row.pair_kind == "EXACT_NAME"),
                near_duplicate_count=sum(1 for row in remaining if row.pair_kind == "NEAR_DUPLICATE"),
            ),
        )

    def list_judged_conflicts(self, limit: int = 50, offset: int = 0) -> JudgedConflictPage:
        """
        The pairs the judge evaluated, read from the review queue instead of the live scan.

        This is the read that was missing. 84 of the 88 decisions on the real collection were
        auto-resolutions, and an auto-resolution deletes the losing row — so those pairs are gone
        from the live scan and their verdicts were unreachable. The queue row survives because
        ``context_payload`` is a snapshot without a foreign key, exactly like the merge proposals'
        ``members``.

        ``tag_alive``/``entity_alive`` are computed in the same query, like the merge proposals'
        ``members_alive``: a decision about a pair that no longer exists is history, and the screen
        must not offer to decide it again. The totals are over the whole queue, because "65
        auto-resolvidas como ENTITY" cannot be derived from one page.
        """
        tag_alive = ArchiveTag.tag_id.is_not(None)
        entity_alive = ArchiveEntity.entity_id.is_not(None)

        stmt = (
            select(
                ArchiveAIReviewQueue.id,
                ArchiveAIReviewQueue.context_payload,
                ArchiveAIReviewQueue.llm_decision,
                ArchiveAIReviewQueue.llm_confidence,
                ArchiveAIReviewQueue.llm_reason,
                ArchiveAIReviewQueue.status,
                tag_alive.label("tag_alive"),
                entity_alive.label("entity_alive"),
                ArchiveConflictResolutionLog.resolution_id,
                ArchiveConflictResolutionLog.undone_at,
            )
            .select_from(ArchiveAIReviewQueue)
            .outerjoin(
                ArchiveTag,
                ArchiveTag.tag_id == ArchiveAIReviewQueue.context_payload["tag_id"].as_integer(),
            )
            .outerjoin(
                ArchiveEntity,
                ArchiveEntity.entity_id == ArchiveAIReviewQueue.context_payload["entity_id"].as_integer(),
            )
            .outerjoin(
                ArchiveConflictResolutionLog,
                (ArchiveConflictResolutionLog.tag_id == ArchiveAIReviewQueue.context_payload["tag_id"].as_integer())
                & (
                    ArchiveConflictResolutionLog.entity_id
                    == ArchiveAIReviewQueue.context_payload["entity_id"].as_integer()
                )
                & (ArchiveConflictResolutionLog.undone_at.is_(None)),
            )
            .where(ArchiveAIReviewQueue.anomaly_type == AnomalyType.CROSS_DOMAIN_COLLISION)
            .order_by(ArchiveAIReviewQueue.id.desc())
        )

        rows = list(self.db.execute(stmt).all())
        items = [
            JudgedConflict(
                queue_id=int(row.id),
                tag_id=int(row.context_payload.get("tag_id", 0)),
                tag_name=str(row.context_payload.get("tag_name", "")),
                entity_id=int(row.context_payload.get("entity_id", 0)),
                entity_name=str(row.context_payload.get("entity_name", "")),
                entity_type=str(row.context_payload.get("entity_type", "")),
                judge_winner=row.llm_decision,
                judge_confidence=row.llm_confidence,
                judge_reason=row.llm_reason,
                judge_status=str(row.status),
                tag_alive=bool(row.tag_alive),
                entity_alive=bool(row.entity_alive),
                resolution_id=int(row.resolution_id) if row.resolution_id is not None else None,
                resolution_undone=False,
            )
            for row in rows
        ]

        return JudgedConflictPage(
            total=len(items),
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
            auto_resolved=sum(1 for item in items if item.judge_status == str(ArchiveReviewStatus.AI_APPROVED)),
            sent_to_human=sum(1 for item in items if item.judge_status == str(ArchiveReviewStatus.NEEDS_REVIEW)),
            tag_wins=sum(1 for item in items if item.judge_winner == "TAG"),
            entity_wins=sum(1 for item in items if item.judge_winner == "ENTITY"),
            still_applicable=sum(1 for item in items if item.applicable),
        )

    def _document_ids_by_tag(self, tag_id: int) -> list[str]:
        return list(
            self.db.scalars(select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id == tag_id)).all()
        )

    def _document_ids_by_entity(self, entity_id: int) -> list[str]:
        return list(
            self.db.scalars(
                select(ArchiveDocumentEntity.description_id).where(ArchiveDocumentEntity.entity_id == entity_id)
            ).all()
        )

    def plan_conflict_resolution(
        self,
        tag_id: int,
        entity_id: int,
        similarity: float = 0.0,
        verdicts: dict[tuple[int, int], dict[str, Any]] | None = None,
        resolutions: dict[tuple[int, int], tuple[int, str, str]] | None = None,
    ) -> ConflictResolutionPlan:
        """
        Everything a resolution would change, computed without writing anything.

        Single definition of the operation: the preview returns this plan and
        :meth:`apply_conflict_resolution` executes it, so the dry run cannot promise a different
        number from the write — the same rule ``TagRepository.plan_merge`` follows.

        Both verdicts are computed, because the archivist's question is comparative. The three facts
        that decide it are: how many documents follow the loser to the winner, how many of those
        already carry the winner (so the transfer changes nothing for them), and whether the ban the
        resolution would plant is already in place.

        ``verdicts`` and ``resolutions`` are the two whole-table reads the plan annotates itself with,
        accepted as arguments so a **batch** can read each once for all of its pairs instead of once
        per pair. Passing them changes nothing about the computation; leaving them out keeps the
        single-pair behaviour.
        """
        tag = self.db.get(ArchiveTag, tag_id)
        entity = self.db.get(ArchiveEntity, entity_id)

        tag_docs = self._document_ids_by_tag(tag_id) if tag is not None else []
        entity_docs = self._document_ids_by_entity(entity_id) if entity is not None else []

        tag_linked = set(tag_docs)
        entity_linked = set(entity_docs)

        # The judge's verdict, so the preview can show what has already been decided.
        verdict = (self._judge_verdicts() if verdicts is None else verdicts).get((tag_id, entity_id), {})
        active_resolutions = self._active_resolutions() if resolutions is None else resolutions
        already_resolved = (tag_id, entity_id) in active_resolutions

        entity_name = entity.name if entity is not None else ""
        tag_name = tag.name if tag is not None else ""

        # The ban each verdict would plant: the losing spelling is banned in the winning axis.
        tag_wins_ban_exists = bool(
            entity_name
            and self.db.scalar(
                select(DomainNerExclusion.term).where(DomainNerExclusion.term == normalize_entity(entity_name))
            )
        )
        entity_wins_ban_exists = bool(
            tag_name
            and self.db.scalar(
                select(DomainStopwords.word).where(
                    DomainStopwords.word == normalize_stopword(tag_name),
                    DomainStopwords.word_scope.in_([StopwordsScope.TAG, StopwordsScope.ALL]),
                )
            )
        )

        blocker: str | None = None
        if tag is None and entity is None:
            blocker = "Nenhum dos dois lados existe mais no vocabulário."
        elif tag is None:
            blocker = f"A tag {tag_id} não existe mais: este par já foi resolvido a favor da entidade."
        elif entity is None:
            blocker = f"A entidade {entity_id} não existe mais: este par já foi resolvido a favor da tag."

        # TAG wins: the entity's documents move to the tag, and the entity disappears. The
        # documents that already carry the tag are counted apart, because nothing changes for them.
        tag_wins_overlap = entity_linked & tag_linked
        # ENTITY wins: the tag's documents move to the entity, and the tag disappears.
        entity_wins_overlap = tag_linked & entity_linked

        return ConflictResolutionPlan(
            tag_id=tag_id,
            tag_name=tag_name,
            tag_document_count=len(tag_docs),
            entity_id=entity_id,
            entity_name=entity_name,
            entity_type=entity.entity_type if entity is not None else "",
            entity_document_count=len(entity_docs),
            similarity=similarity,
            tag_alive=tag is not None,
            entity_alive=entity is not None,
            already_resolved=already_resolved,
            judge_winner=verdict.get("judge_winner"),
            judge_confidence=verdict.get("judge_confidence"),
            judge_reason=verdict.get("judge_reason"),
            tag_wins_documents_transferred=len(entity_docs) - len(tag_wins_overlap),
            tag_wins_documents_already_linked=len(tag_wins_overlap),
            tag_wins_loses=entity_name or None,
            tag_wins_ban_term=entity_name or None,
            tag_wins_ban_exists=tag_wins_ban_exists,
            entity_wins_documents_transferred=len(tag_docs) - len(entity_wins_overlap),
            entity_wins_documents_already_linked=len(entity_wins_overlap),
            entity_wins_loses=tag_name or None,
            entity_wins_ban_term=tag_name or None,
            entity_wins_ban_exists=entity_wins_ban_exists,
            resolvable=blocker is None,
            blocker=blocker,
        )

    def apply_conflict_resolution(
        self,
        plan: ConflictResolutionPlan,
        winner: ConflictWinner,
        source: ConflictDecider = "HUMAN",
        decided_by: Author | None = None,
        note: str | None = None,
    ) -> ConflictResolutionData:
        """
        Executes the plan and writes the ledger row that makes it reversible.

        The ledger is written **before** the destructive half: if the delete succeeded and the row
        were lost, the documents would already have moved and nothing would describe how to put them
        back. ``TagRepository.apply_merge`` follows the same order for the same reason.

        Returns what was written, including the ``resolution_id`` the screen needs to offer the undo.
        """
        if not plan.resolvable:
            raise UnresolvableConflictError(plan.blocker or "Este par não pode mais ser resolvido.")

        if winner == "TAG" and not plan.entity_alive:
            raise UnresolvableConflictError("A entidade deste par não existe mais.")
        if winner == "ENTITY" and not plan.tag_alive:
            raise UnresolvableConflictError("A tag deste par não existe mais.")

        if winner == "TAG":
            loser_docs = self._document_ids_by_entity(plan.entity_id)
            winner_links = set(self._document_ids_by_tag(plan.tag_id))
            ban_kind = "NER_EXCLUSION"
            ban_term = plan.entity_name
            ban_exists = plan.tag_wins_ban_exists
        else:
            loser_docs = self._document_ids_by_tag(plan.tag_id)
            winner_links = set(self._document_ids_by_entity(plan.entity_id))
            ban_kind = "STOPWORD"
            ban_term = plan.tag_name
            ban_exists = plan.entity_wins_ban_exists

        # Exactly the links this resolution creates: the ones that were not there before. Without
        # this subset the undo would delete links that predate the resolution.
        created_link_ids = sorted(document_id for document_id in loser_docs if document_id not in winner_links)

        row = ArchiveConflictResolutionLog(
            winner=winner,
            source=source,
            tag_id=plan.tag_id,
            tag_name=plan.tag_name,
            entity_id=plan.entity_id,
            entity_name=plan.entity_name,
            entity_type=plan.entity_type,
            loser_snapshot=self._loser_snapshot(winner, plan),
            # The spellings the delete cascades. Recorded here because this path deletes the loser
            # by id while the NER purge deletes by name, and the two have to restore the same things
            # (#94, constitution IV).
            synonym_names=self._loser_synonym_names(winner, plan),
            transferred_document_ids=sorted(loser_docs),
            created_link_ids=created_link_ids,
            ban_kind=ban_kind,
            ban_term=ban_term,
            ban_created=not ban_exists,
            **author_columns("decided_by", decided_by),
            note=note,
        )
        self.db.add(row)
        self.db.flush()

        transferred = self._transfer_conflict_winner(winner, plan, loser_docs, created_link_ids, source, ban_exists)

        return ConflictResolutionData(
            winner=winner,
            documents_transferred=transferred,
            resolution_id=row.resolution_id,
            ban_kind=ban_kind,
            ban_term=ban_term,
        )

    def _loser_snapshot(self, winner: ConflictWinner, plan: ConflictResolutionPlan) -> dict[str, Any]:
        """The full losing row, so the undo restores it instead of an approximation."""
        loser: ArchiveTag | ArchiveEntity | None = (
            self.db.get(ArchiveEntity, plan.entity_id) if winner == "TAG" else self.db.get(ArchiveTag, plan.tag_id)
        )

        if loser is None:
            return {}
        return {column.name: _jsonable(getattr(loser, column.name)) for column in loser.__table__.columns}

    def _loser_synonym_names(self, winner: ConflictWinner, plan: ConflictResolutionPlan) -> list[str]:
        """
        The spellings the losing row absorbs today, in its own axis.

        ``domain_synonyms`` cascades on both canonical keys, so the delete takes these with the row;
        recording them is what lets ``undo_conflict_resolution`` put them back, exactly as the NER
        purge records the entity's. Two axes, one rule.
        """
        if winner == "TAG":
            return self._entity_synonym_names_by_id([plan.entity_id]).get(plan.entity_id, [])

        stmt = select(DomainSynonyms.synonym_name).where(
            DomainSynonyms.category == "TAG", DomainSynonyms.canonical_tag_id == plan.tag_id
        )
        return sorted(set(self.db.scalars(stmt).all()))

    def _transfer_conflict_winner(
        self,
        winner: ConflictWinner,
        plan: ConflictResolutionPlan,
        loser_docs: Sequence[str],
        created_link_ids: Sequence[str],
        source: ConflictDecider,
        ban_exists: bool,
    ) -> int:
        """
        Moves the loser's documents to the winner, deletes the loser and plants the ban.

        The insert is ``ON CONFLICT DO NOTHING``: a document that already carried the winner keeps
        its single link, and ``created_link_ids`` (computed by the caller) records which links are
        new so the undo removes only those.
        """
        transferred = 0

        if winner == "TAG":
            if created_link_ids:
                self.db.execute(
                    insert(ArchiveDocumentTag)
                    .values([{"description_id": d, "tag_id": plan.tag_id} for d in created_link_ids])
                    .on_conflict_do_nothing()
                )
            transferred = len(created_link_ids)
            self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id == plan.entity_id))
            if plan.entity_name and not ban_exists:
                # The subject axis owns the spelling: an exclusion, not a generic stopword, so the
                # decision stays auditable and reversible.
                self.add_ner_exclusions(
                    [plan.entity_name],
                    source=source,
                    reason="cross-domain clash: the TAG won over the named entity",
                    tag_id=plan.tag_id,
                )
        else:
            if created_link_ids:
                self.db.execute(
                    insert(ArchiveDocumentEntity)
                    .values([{"description_id": d, "entity_id": plan.entity_id} for d in created_link_ids])
                    .on_conflict_do_nothing()
                )
            transferred = len(created_link_ids)
            self.db.execute(delete(ArchiveTag).where(ArchiveTag.tag_id == plan.tag_id))
            if plan.tag_name and not ban_exists:
                self.db.execute(
                    insert(DomainStopwords)
                    .values(word=normalize_stopword(plan.tag_name), word_scope=StopwordsScope.TAG)
                    .on_conflict_do_nothing()
                )

        # Flush so a structural failure (a constraint on the re-inserted links) surfaces here,
        # inside the caller's savepoint, instead of at the next unrelated statement.
        self.db.flush()
        return transferred

    def undo_conflict_resolution(
        self, resolution_id: int, undone_by: Author | None = None
    ) -> ConflictResolutionLogEntry:
        """
        Reverses one resolution: the losing row comes back, its links come back, the ban goes.

        Exact by construction, like ``TagRepository.undo_merge``: the row is rebuilt from the
        snapshot (every column, including the id the sequence already allocated), only the links the
        resolution created are removed, and the ban is lifted only when this resolution planted it —
        a ban an earlier decision wrote is not this undo's business.
        """
        row = self.db.get(ArchiveConflictResolutionLog, resolution_id)
        if row is None:
            raise ConflictResolutionNotFoundError(f"Resolução {resolution_id} não encontrada no ledger.")
        if row.undone_at is not None:
            raise ConflictResolutionAlreadyUndoneError(
                f"A resolução {resolution_id} já foi desfeita em {row.undone_at:%Y-%m-%d %H:%M:%S}."
            )

        snapshot = row.loser_snapshot or {}
        if snapshot:
            if row.winner == "TAG":
                restored_entity = ArchiveEntity(
                    entity_id=row.entity_id,
                    name=snapshot.get("name") or row.entity_name,
                    entity_type=snapshot.get("entity_type") or row.entity_type,
                )
                if snapshot.get("created_at"):
                    restored_entity.created_at = datetime.fromisoformat(str(snapshot["created_at"]))
                self.db.add(restored_entity)
            else:
                restored_tag = ArchiveTag(
                    tag_id=row.tag_id,
                    name=snapshot.get("name") or row.tag_name,
                    macro_category_id=snapshot.get("macro_category_id"),
                    ai_confidence_score=snapshot.get("ai_confidence_score"),
                    execution_log=snapshot.get("execution_log"),
                )
                if snapshot.get("created_at"):
                    restored_tag.created_at = datetime.fromisoformat(str(snapshot["created_at"]))
                self.db.add(restored_tag)
            self.db.flush()
            # After the row exists (its FK is the target of these spellings) and before the ledger
            # row is marked undone.
            self._restore_conflict_spellings(row)

        self._remove_created_conflict_links(row)
        self._restore_conflict_links(row)
        self._lift_conflict_ban(row)

        row.undone_at = datetime.now(UTC)
        assign_author(row, "undone_by", undone_by)
        self.db.flush()
        return self._to_resolution_entry(row)

    def _remove_created_conflict_links(self, row: ArchiveConflictResolutionLog) -> int:
        """Drops the links the resolution created, leaving the pre-resolution ones alone."""
        created = list(row.created_link_ids or [])
        if not created:
            return 0

        if row.winner == "TAG":
            stmt = delete(ArchiveDocumentTag).where(
                ArchiveDocumentTag.tag_id == row.tag_id,
                ArchiveDocumentTag.description_id.in_(created),
            )
        else:
            stmt = delete(ArchiveDocumentEntity).where(
                ArchiveDocumentEntity.entity_id == row.entity_id,
                ArchiveDocumentEntity.description_id.in_(created),
            )
        return cast(CursorResult, self.db.execute(stmt)).rowcount

    def _restore_conflict_links(self, row: ArchiveConflictResolutionLog) -> int:
        """
        Re-links the documents that carried the restored row.

        Only documents that still exist: one deleted after the resolution must not make the undo
        impossible, which is the same care ``TagRepository._relink_documents`` takes.
        """
        documents = list(row.transferred_document_ids or [])
        if not documents:
            return 0

        existing = set(
            self.db.scalars(
                select(ArchiveDocument.description_id).where(ArchiveDocument.description_id.in_(documents))
            ).all()
        )
        if not existing:
            return 0

        if row.winner == "TAG":
            stmt = insert(ArchiveDocumentEntity).values(
                [{"description_id": d, "entity_id": row.entity_id} for d in sorted(existing)]
            )
        else:
            stmt = insert(ArchiveDocumentTag).values(
                [{"description_id": d, "tag_id": row.tag_id} for d in sorted(existing)]
            )
        self.db.execute(stmt.on_conflict_do_nothing())
        return len(existing)

    def _restore_conflict_spellings(self, row: ArchiveConflictResolutionLog) -> None:
        """
        Puts back the spellings the delete cascaded, pointed at the restored row.

        ``on_conflict_do_nothing``: a mapping somebody re-created after the resolution points
        wherever they put it, and that is not this undo's business — the same care
        ``TagRepository._restore_purged_spellings`` takes.
        """
        names = list(row.synonym_names or [])
        if not names:
            return

        if row.winner == "TAG":
            self._restore_entity_spelling_names(row.entity_id, names, row.entity_type)
            return

        rows = [{"synonym_name": name, "category": "TAG", "canonical_tag_id": row.tag_id} for name in names]
        stmt = insert(DomainSynonyms).values(rows).on_conflict_do_nothing(index_elements=["synonym_name", "category"])
        self.db.execute(stmt)

    def _lift_conflict_ban(self, row: ArchiveConflictResolutionLog) -> int:
        """
        Removes the ban this resolution planted — and only when it planted it.

        ``ban_created`` is the guard: the ban is written with ``ON CONFLICT DO NOTHING``, so a
        spelling an earlier resolution had already banned must survive the reversal of a later one.
        """
        if not row.ban_created or not row.ban_term:
            return 0

        if row.ban_kind == "NER_EXCLUSION":
            stmt = delete(DomainNerExclusion).where(DomainNerExclusion.term == normalize_entity(row.ban_term))
        elif row.ban_kind == "STOPWORD":
            stmt = delete(DomainStopwords).where(
                DomainStopwords.word == normalize_stopword(row.ban_term),
                DomainStopwords.word_scope.in_([StopwordsScope.TAG, StopwordsScope.ALL]),
            )
        else:
            return 0
        return cast(CursorResult, self.db.execute(stmt)).rowcount

    def list_conflict_resolutions(
        self, include_undone: bool = True, limit: int = 50, offset: int = 0
    ) -> tuple[list[ConflictResolutionLogEntry], int]:
        """One page of the ledger, newest first, with the total matching the same filter."""
        conditions = [] if include_undone else [ArchiveConflictResolutionLog.undone_at.is_(None)]

        total = int(
            self.db.scalar(select(func.count()).select_from(ArchiveConflictResolutionLog).where(*conditions)) or 0
        )
        stmt = (
            select(ArchiveConflictResolutionLog)
            .where(*conditions)
            .order_by(ArchiveConflictResolutionLog.resolution_id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.db.scalars(stmt).all())
        return [self._to_resolution_entry(row) for row in rows], total

    def _to_resolution_entry(self, row: ArchiveConflictResolutionLog) -> ConflictResolutionLogEntry:
        """Read view of one ledger row, with "is the loser back?" derived on read."""
        loser_restored = False
        if row.undone_at is not None:
            if row.winner == "TAG":
                loser_restored = self.db.get(ArchiveEntity, row.entity_id) is not None
            else:
                loser_restored = self.db.get(ArchiveTag, row.tag_id) is not None

        return ConflictResolutionLogEntry(
            resolution_id=row.resolution_id,
            winner=cast(ConflictWinner, row.winner),
            source=cast(ConflictDecider, row.source),
            tag_id=row.tag_id,
            tag_name=row.tag_name,
            entity_id=row.entity_id,
            entity_name=row.entity_name,
            entity_type=row.entity_type,
            documents_transferred=len(row.transferred_document_ids or []),
            ban_kind=cast(ConflictBanKind | None, row.ban_kind),
            ban_term=row.ban_term,
            ban_created=row.ban_created,
            decided_by=row.decided_by,
            decided_at=row.decided_at,
            note=row.note,
            undone_at=row.undone_at,
            undone_by=row.undone_by,
            loser_restored=loser_restored,
        )

    def resolve_cross_domain_conflict(
        self,
        winner: Literal["TAG", "ENTITY"],
        tag_id: int,
        entity_id: int,
        source: NerExclusionSource = "HUMAN",
        decided_by: Author | None = None,
    ) -> int:
        """
        Plan and apply in one call, through the ledger.

        Kept as the single entry point for callers that have no reason to inspect the impact first
        (the judge worker, which has already made the decision), so no path can write a resolution
        that leaves no trace. The API uses the two halves separately, because the archivist is
        entitled to see the numbers before the write.
        """
        plan = self.plan_conflict_resolution(tag_id, entity_id)
        data = self.apply_conflict_resolution(plan, winner, source=source, decided_by=decided_by)
        return data.documents_transferred

    # --- Ingestion and NER Methods ---

    def get_ner_synonyms_rules(self) -> list[NerSynonymRule]:
        """
        Loads the semantic normalization rules exclusive to the NER pipeline (spaCy).
        Ignores TAG synonyms, returning only mappings to Canonical Entities.

        Spellings recorded in the NER exclusion catalog are dropped: an excluded term
        must not re-enter through the positive dictionary either.
        """

        stmt = (
            select(DomainSynonyms.synonym_name, DomainSynonyms.category, ArchiveEntity.name.label("canonical_entity"))
            .join(ArchiveEntity, DomainSynonyms.canonical_entity_id == ArchiveEntity.entity_id)
            .where(DomainSynonyms.category.in_(["ORG", "LOC", "PER"]))
            .where(~DomainSynonyms.synonym_name.in_(select(DomainNerExclusion.term)))
        )

        results = self.db.execute(stmt).all()

        # ``id`` is the key spaCy reads from a phrase pattern to fill ``ent_id_``.
        return [
            NerSynonymRule(pattern=row.synonym_name, label=row.category, id=row.canonical_entity) for row in results
        ]

    # --- NER exclusions: the subject axis owns the spelling ---

    def get_ner_exclusion_terms(self) -> set[str]:
        """Terms the curation excluded from NER extraction, normalized to lowercase."""
        return set(self.db.scalars(select(DomainNerExclusion.term)).all())

    def list_ner_exclusions(self) -> Sequence[NerExclusion]:
        """Full catalog, ordered by term, for the curation API."""
        stmt = select(DomainNerExclusion).order_by(DomainNerExclusion.term)
        return [NerExclusion.model_validate(row) for row in self.db.scalars(stmt).all()]

    def add_ner_exclusions(
        self,
        terms: Sequence[str],
        *,
        source: NerExclusionSource = "HUMAN",
        reason: str | None = None,
        tag_id: int | None = None,
    ) -> int:
        """Registers exclusions idempotently. Returns how many terms were actually inserted."""
        rows = [
            {"term": normalize_entity(term), "source": source, "reason": reason, "tag_id": tag_id}
            for term in terms
            if term.strip()
        ]

        if not rows:
            return 0

        stmt = insert(DomainNerExclusion).values(rows).on_conflict_do_nothing(index_elements=["term"])
        result = cast(CursorResult, self.db.execute(stmt))
        return result.rowcount

    def remove_ner_exclusions(self, terms: Sequence[str]) -> int:
        """Re-opens NER for the given terms. Returns how many exclusions were removed."""
        clean_terms = [normalize_entity(term) for term in terms if term.strip()]

        if not clean_terms:
            return 0

        result = self.db.execute(delete(DomainNerExclusion).where(DomainNerExclusion.term.in_(clean_terms)))
        return cast(CursorResult, result).rowcount

    # --- The NER purge: the destructive half of the veto, on its own ---
    #
    # One operation in two halves, exactly like the stopword purge: ``plan_ner_purge`` describes
    # what would die without writing, and ``apply_ner_purge`` executes that same plan after
    # snapshotting every entity in ``archive_ner_purge_log``. The preview reads the plan and the
    # write consumes it, so the two cannot disagree about which entities the purge acts on. There
    # is no repoint step, unlike the merge: the spelling is banned, so its entity's spellings have
    # nowhere to go — they are recorded for the undo and the forward write leaves them to the
    # cascade. The undo does **not** lift the veto: restoring the entity is not un-banning the term.

    def plan_ner_purge(self) -> NerPurgePlan:
        """
        Every entity the purge would delete, with the state the undo has to rebuild.

        The terms come from ``domain_ner_exclusions`` — the banned spellings — and the per-entity
        documents and spellings are read here so the ledger records what the delete is about to
        cascade instead of reconstructing it afterwards.
        """
        terms = sorted(self.get_ner_exclusion_terms())
        if not terms:
            return NerPurgePlan()

        entities = self.db.scalars(select(ArchiveEntity).where(func.lower(ArchiveEntity.name).in_(terms))).all()
        if not entities:
            return NerPurgePlan(excluded_terms=terms)

        entity_ids = [entity.entity_id for entity in entities]
        documents_by_entity = self.get_document_ids_grouped_by_entities(entity_ids)
        spellings_by_entity = self._entity_synonym_names_by_id(entity_ids)
        items = [
            NerPurgeItem(
                entity_id=entity.entity_id,
                name=entity.name,
                entity_type=entity.entity_type,
                excluded_term=normalize_entity(entity.name),
                document_ids=documents_by_entity.get(entity.entity_id, []),
                synonym_names=spellings_by_entity.get(entity.entity_id, []),
                created_at=entity.created_at,
            )
            for entity in entities
        ]
        # Heaviest first, then by name: the order the stopword preview already shows, so the two
        # surfaces read the same way and the screen does not reshuffle under the archivist.
        items.sort(key=lambda item: (-len(item.document_ids), item.name))
        return NerPurgePlan(excluded_terms=terms, items=items)

    def write_ner_purge_log(self, plan: NerPurgePlan, changed_by: Author | None = None) -> list[int]:
        """
        Snapshots every entity the plan deletes. Returns the ledger ids, oldest first.

        Written **before** anything changes, because what it captures — the documents and the
        spellings that pointed at the entity — is exactly what the delete cascades.
        """
        if not plan.items:
            return []

        rows = [
            {
                "excluded_term": item.excluded_term,
                "purged_entity_id": item.entity_id,
                "purged_name": normalize_entity(item.name),
                "purged_snapshot": {
                    "name": item.name,
                    "entity_type": item.entity_type,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                },
                "document_ids": item.document_ids,
                "synonym_names": item.synonym_names,
                **author_columns("changed_by", changed_by),
            }
            for item in plan.items
        ]
        stmt = insert(ArchiveNerPurgeLog).values(rows).returning(ArchiveNerPurgeLog.purge_id)
        return list(self.db.scalars(stmt).all())

    def apply_ner_purge(self, plan: NerPurgePlan, changed_by: Author | None = None) -> NerPurgeResult:
        """Executes exactly what ``plan_ner_purge`` described, after writing the undo ledger."""
        purge_ids = self.write_ner_purge_log(plan, changed_by=changed_by)
        deleted = self.delete_entities([item.entity_id for item in plan.items]) if plan.items else 0
        return NerPurgeResult(entities_deleted=deleted, purge_ids=purge_ids)

    def undo_ner_purge(self, purge_id: int, undone_by: Author | None = None) -> NerPurgeLogEntryDTO:
        """
        Reverses one purge: restores the entity, its links and its spellings.

        Exact by construction, like ``undo_stopword_purge``: the id and the row come from the
        snapshot, the links from the per-entity list and the spellings from what was captured
        before the delete. Only documents that still exist are re-linked. The veto is **not**
        lifted — the term is still excluded; the undo restores the entity, it does not undo the
        decision to ban the spelling.
        """
        row = self.db.get(ArchiveNerPurgeLog, purge_id)
        if row is None:
            raise NerPurgeLogNotFoundError(f"Registro de purga de NER {purge_id} não encontrado no ledger.")
        if row.undone_at is not None:
            raise NerPurgeAlreadyUndoneError(
                f"A purga de NER {purge_id} já foi desfeita em {row.undone_at:%Y-%m-%d %H:%M:%S}."
            )

        snapshot = row.purged_snapshot or {}
        entity_type = snapshot.get("entity_type") or "ORG"
        restored = ArchiveEntity(
            entity_id=row.purged_entity_id,
            name=snapshot.get("name") or row.purged_name,
            entity_type=entity_type,
        )
        created_at = snapshot.get("created_at")
        if created_at:
            restored.created_at = datetime.fromisoformat(created_at)
        self.db.add(restored)
        self.db.flush()

        self._relink_entity_documents(row.purged_entity_id, row.document_ids or [])
        self._restore_entity_spelling_names(row.purged_entity_id, row.synonym_names or [], entity_type)

        row.undone_at = datetime.now(UTC)
        assign_author(row, "undone_by", undone_by)
        self.db.flush()
        return self._to_ner_purge_log_dto(row)

    def _restore_entity_spelling_names(self, entity_id: int, names: Sequence[str], category: str | None) -> None:
        """
        Puts the spellings back the cascade took with the entity.

        ``on_conflict_do_nothing`` on ``(synonym_name, category)``: a mapping somebody re-created
        after the purge points wherever they put it, and that is not this undo's business. The
        category is the entity's own type, snapshotted at purge time — the one the spellings were
        written under.
        """
        if not names or not category:
            return

        rows = [{"synonym_name": name, "category": category, "canonical_entity_id": entity_id} for name in names]
        stmt = insert(DomainSynonyms).values(rows).on_conflict_do_nothing(index_elements=["synonym_name", "category"])
        self.db.execute(stmt)

    def _entity_synonym_names_by_id(self, entity_ids: Sequence[int]) -> dict[int, list[str]]:
        """Spellings each entity absorbs today, keyed by the entity they point at."""
        if not entity_ids:
            return {}

        stmt = select(DomainSynonyms.canonical_entity_id, DomainSynonyms.synonym_name).where(
            DomainSynonyms.category.in_(list(ENTITY_SYNONYM_CATEGORIES)),
            DomainSynonyms.canonical_entity_id.in_(list(entity_ids)),
        )
        grouped: dict[int, list[str]] = defaultdict(list)
        for canonical_entity_id, synonym_name in self.db.execute(stmt).all():
            if canonical_entity_id is not None:
                grouped[canonical_entity_id].append(synonym_name)
        return {entity_id: sorted(names) for entity_id, names in grouped.items()}

    def _ner_purge_log_filters(self, include_undone: bool, term: str | None = None) -> list[Any]:
        """The filters of the purge ledger, including the free-text one over the entity name."""
        filters: list[Any] = []
        if not include_undone:
            filters.append(ArchiveNerPurgeLog.undone_at.is_(None))
        if term:
            pattern = f"%{escape_like(term)}%"
            filters.append(ArchiveNerPurgeLog.purged_name.ilike(pattern, escape=LIKE_ESCAPE))
        return filters

    def count_ner_purge_log(self, include_undone: bool = True, term: str | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(ArchiveNerPurgeLog)
            .where(*self._ner_purge_log_filters(include_undone, term))
        )
        return self.db.scalar(stmt) or 0

    def list_ner_purge_log(
        self,
        include_undone: bool = True,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NerPurgeLogListResponse:
        """The audit trail: most recent first, undone entries included unless filtered out."""
        total = self.count_ner_purge_log(include_undone=include_undone, term=term)
        stmt = (
            select(ArchiveNerPurgeLog)
            .where(*self._ner_purge_log_filters(include_undone, term))
            .order_by(ArchiveNerPurgeLog.purge_id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = self.db.scalars(stmt).all()
        return NerPurgeLogListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[self._to_ner_purge_log_dto(row) for row in rows],
        )

    def get_ner_purge_log_entry(self, purge_id: int) -> NerPurgeLogEntryDTO | None:
        row = self.db.get(ArchiveNerPurgeLog, purge_id)
        if row is None:
            return None
        return self._to_ner_purge_log_dto(row)

    def _to_ner_purge_log_dto(self, row: ArchiveNerPurgeLog) -> NerPurgeLogEntryDTO:
        """Maps the row to the read contract, exposing the document *count* and not the ids."""
        snapshot = row.purged_snapshot or {}
        return NerPurgeLogEntryDTO(
            purge_id=row.purge_id,
            purged_entity_id=row.purged_entity_id,
            purged_name=row.purged_name,
            entity_type=snapshot.get("entity_type") or "",
            excluded_term=row.excluded_term,
            document_count=len(row.document_ids or []),
            synonym_names=list(row.synonym_names or []),
            changed_by=row.changed_by,
            changed_at=row.changed_at,
            undone_at=row.undone_at,
            undone_by=row.undone_by,
        )

    def get_or_create_entities(self, entities_list: list[ArchiveEntityDTO]) -> list[int]:
        """
        Manages the entity dimension (NER).

        Receives a list of People, Organizations or Locations identified by the AI.
        Uses ON CONFLICT DO NOTHING to guarantee uniqueness by name.

        Returns:
            list[int]: List of IDs (Primary Keys) of the entities ready for linking.
        """

        if not entities_list:
            return []

        # 1. Prepares the list of dictionaries for the mass INSERT.
        # Names are normalized to lowercase (mirroring the Tag dimension) so that
        # "Cidade" and "cidade" resolve to the same canonical entity.
        insert_data = []
        names_to_search = []

        for ent in entities_list:
            name_clean = normalize_entity(ent.name)
            names_to_search.append(name_clean)
            insert_data.append({"name": name_clean, "entity_type": ent.entity_type})

        # 2. Performs the mass INSERT ignoring entities that already exist (unique index on 'name')
        stmt_insert = insert(ArchiveEntity).values(insert_data).on_conflict_do_nothing(index_elements=["name"])
        self.db.execute(stmt_insert)

        # 3. In a SINGLE select, fetches all IDs (both the newly created and the already existing ones)
        stmt_select = select(ArchiveEntity.entity_id).where(ArchiveEntity.name.in_(names_to_search))

        return list(self.db.scalars(stmt_select).all())

    # --- Methods for the Merge ---

    def link_documents_to_entity(self, doc_ids: set[str], target_entity_id: int) -> None:
        new_links = [{"description_id": doc_id, "entity_id": target_entity_id} for doc_id in doc_ids]
        stmt = insert(ArchiveDocumentEntity).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def link_entities_to_document(self, description_id: str, entity_ids: list[int]) -> None:
        """Links multiple entities to a single document (Used in Ingestion / Worker)."""
        if not entity_ids:
            return

        # We use set(entity_ids) to avoid trying to insert the same entity twice in the same document
        new_links = [{"description_id": description_id, "entity_id": e_id} for e_id in set(entity_ids)]
        stmt = insert(ArchiveDocumentEntity).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def bulk_link_entities(self, links: Sequence[EntityLinkCommand]) -> None:
        """
        Optimization for Batch Ingestion (Workers).
        Inserts thousands of N:N links in a single transaction, deduplicating
        identical commands so the database does not take unnecessary locks.
        """
        if not links:
            return

        unique_links = {(link.description_id, link.entity_id) for link in links}
        rows = [
            {"description_id": description_id, "entity_id": entity_id} for description_id, entity_id in unique_links
        ]

        stmt = insert(ArchiveDocumentEntity).values(rows).on_conflict_do_nothing()
        self.db.execute(stmt)

    def create_synonyms(self, synonyms_data: list[SynonymCommand]) -> None:
        """
        Registers the spellings the NER must redirect to a canonical entity.

        The write itself is defined once, in
        :func:`scrinalia.domains.archive.repository.synonym_upsert.upsert_synonyms`, because the two
        axes used to carry the same command twice and one of them drifted into a 500.
        """
        upsert_synonyms(self.db, synonyms_data)

    def repoint_synonyms(self, from_entity_ids: list[int], to_entity_id: int) -> int:
        """
        Moves every synonym that pointed at an entity being merged onto the surviving one.

        ``domain_synonyms.canonical_entity_id`` is ``ON DELETE CASCADE``: without this step,
        deleting the absorbed entity destroys the spellings already absorbed into it and the
        next extraction recreates them as brand-new entities — the curation undone by the very
        merge meant to make it durable. Same defect and same fix as the tag path.
        """
        if not from_entity_ids or to_entity_id in from_entity_ids:
            return 0

        stmt = (
            update(DomainSynonyms)
            .where(
                DomainSynonyms.category.in_(["ORG", "PER", "LOC"]),
                DomainSynonyms.canonical_entity_id.in_(from_entity_ids),
            )
            .values(canonical_entity_id=to_entity_id)
        )
        return cast(CursorResult, self.db.execute(stmt)).rowcount

    def delete_entities(self, entity_ids: list[int]) -> int:
        # The associative deletion (ArchiveDocumentEntity) also lives here
        self.db.execute(delete(ArchiveDocumentEntity).where(ArchiveDocumentEntity.entity_id.in_(entity_ids)))

        result = self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id.in_(entity_ids)))
        return cast(CursorResult, result).rowcount

    def update_entity_type(self, entity_id: int, new_type: str) -> None:
        """Updates the category (PER, LOC, ORG) of a canonical entity."""
        # Adjust 'Entity' to the exact name of your SQLAlchemy Model class
        entity = self.db.query(ArchiveEntity).filter(ArchiveEntity.entity_id == entity_id).first()
        if entity:
            entity.entity_type = new_type

    # --- The entity merge: plan, ledger, apply and undo ---
    #
    # One operation in two halves, exactly like the tag merge: ``plan_entity_merge`` describes the
    # impact without writing and ``apply_entity_merge`` executes that same plan, so the dry run and
    # the write cannot promise different numbers. The write is logged **before** anything changes,
    # and the undo restores the row, its links and the spelling state from that snapshot.

    def get_entities_with_counts(self, entity_ids: Sequence[int]) -> dict[int, EntityMergeImpact]:
        """
        Name, type and weight of each entity, orphans included.

        ``get_relevance_count`` is the screen's read: it orders by weight and drops the names no
        description carries. The plan cannot use it — an orphan is exactly a row a merge can absorb
        and a preview has to name — so the count is an outer join and the limit is the id list.
        """
        ids = list(dict.fromkeys(entity_ids))
        if not ids:
            return {}

        counts = (
            select(ArchiveDocumentEntity.entity_id, func.count().label("document_count"))
            .where(ArchiveDocumentEntity.entity_id.in_(ids))
            .group_by(ArchiveDocumentEntity.entity_id)
            .subquery()
        )
        stmt = (
            select(
                ArchiveEntity.entity_id,
                ArchiveEntity.name,
                ArchiveEntity.entity_type,
                func.coalesce(counts.c.document_count, 0),
            )
            .outerjoin(counts, counts.c.entity_id == ArchiveEntity.entity_id)
            .where(ArchiveEntity.entity_id.in_(ids))
        )
        return {
            entity_id: EntityMergeImpact(
                entity_id=entity_id, name=name, entity_type=entity_type, document_count=document_count
            )
            for entity_id, name, entity_type, document_count in self.db.execute(stmt).all()
        }

    def get_document_ids_grouped_by_entities(self, entity_ids: Sequence[int]) -> dict[int, list[str]]:
        """Which documents carry each entity, in one query (the ledger needs the per-entity links)."""
        if not entity_ids:
            return {}

        stmt = select(ArchiveDocumentEntity.entity_id, ArchiveDocumentEntity.description_id).where(
            ArchiveDocumentEntity.entity_id.in_(list(entity_ids))
        )
        grouped: dict[int, list[str]] = defaultdict(list)
        for entity_id, description_id in self.db.execute(stmt).all():
            grouped[entity_id].append(description_id)
        return {entity_id: sorted(ids) for entity_id, ids in grouped.items()}

    def get_entity_synonym_names(self) -> set[str]:
        """Every spelling already anchored to an entity, on any of the three categories."""
        stmt = select(DomainSynonyms.synonym_name).where(DomainSynonyms.category.in_(list(ENTITY_SYNONYM_CATEGORIES)))
        return set(self.db.scalars(stmt).all())

    def get_synonym_names_pointing_to_entities(self, entity_ids: Sequence[int]) -> list[str]:
        """Spellings each entity absorbs today (a merge moves them to the canonical)."""
        if not entity_ids:
            return []

        stmt = select(DomainSynonyms.synonym_name).where(
            DomainSynonyms.category.in_(list(ENTITY_SYNONYM_CATEGORIES)),
            DomainSynonyms.canonical_entity_id.in_(list(entity_ids)),
        )
        return sorted(set(self.db.scalars(stmt).all()))

    def get_entity_synonym_targets(self, names: Sequence[str], category: str) -> dict[str, int]:
        """Where each spelling points today, in one category, so the undo can restore that mapping."""
        if not names:
            return {}

        stmt = select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_entity_id).where(
            DomainSynonyms.category == category, DomainSynonyms.synonym_name.in_(list(names))
        )
        return {
            synonym_name: canonical_entity_id
            for synonym_name, canonical_entity_id in self.db.execute(stmt).all()
            if canonical_entity_id is not None
        }

    def _entity_synonym_names_by_canonical(self, entity_ids: Sequence[int]) -> dict[int, list[str]]:
        """Spellings each entity absorbs today, keyed by the entity they point at."""
        if not entity_ids:
            return {}

        stmt = select(DomainSynonyms.canonical_entity_id, DomainSynonyms.synonym_name).where(
            DomainSynonyms.category.in_(list(ENTITY_SYNONYM_CATEGORIES)),
            DomainSynonyms.canonical_entity_id.in_(list(entity_ids)),
        )
        grouped: dict[int, list[str]] = defaultdict(list)
        for canonical_entity_id, synonym_name in self.db.execute(stmt).all():
            if canonical_entity_id is not None:
                grouped[canonical_entity_id].append(synonym_name)
        return grouped

    def plan_entity_merge(
        self, canonical_id: int, ids_to_merge: Sequence[int], new_name: str | None = None
    ) -> EntityMergePlan:
        """
        Everything the merge would change, computed without writing anything.

        Single definition of the operation: the dry-run returns this plan (trimmed) and
        ``apply_entity_merge`` executes it, so the preview cannot promise something different from
        what the merge does. Same reasoning as the tag ``plan_merge``.
        """
        catalog = self.get_entities_with_counts([canonical_id, *ids_to_merge])
        canonical = catalog.get(canonical_id)
        if canonical is None:
            raise InvalidParam(f"A entidade canônica informada (ID {canonical_id}) não existe no acervo.")

        dead_ids = [
            entity_id for entity_id in dict.fromkeys(ids_to_merge) if entity_id != canonical_id and entity_id in catalog
        ]
        impacted = [catalog[entity_id] for entity_id in dead_ids]

        documents_by_entity = self.get_document_ids_grouped_by_entities(dead_ids)
        document_ids = sorted({doc for docs in documents_by_entity.values() for doc in docs})
        synonym_names = [normalize_entity(member.name) for member in impacted]
        repointed = sorted(set(self.get_synonym_names_pointing_to_entities(dead_ids)))

        rename_from: str | None = None
        rename_to: str | None = None
        if new_name and new_name.strip() and normalize_entity(new_name) != normalize_entity(canonical.name):
            rename_from = canonical.name
            rename_to = new_name.strip()
            # The old canonical spelling becomes a synonym, so the extractor keeps resolving it.
            synonym_names.append(normalize_entity(canonical.name))

        flags: list[str] = []
        if any(has_digits(member.name) for member in impacted):
            flags.append(REVIEW_MEMBER_WITH_DIGITS)
        if any(member.entity_type != canonical.entity_type for member in impacted):
            flags.append(REVIEW_MIXED_TYPES)
        if any(member.document_count == 0 for member in impacted):
            flags.append(REVIEW_ORPHAN_MEMBER)
        if set(synonym_names) & self.get_entity_synonym_names():
            flags.append(REVIEW_MEMBER_IS_SYNONYM)

        return EntityMergePlan(
            canonical_id=canonical_id,
            canonical_name=canonical.name,
            canonical_entity_type=canonical.entity_type,
            canonical_document_count=canonical.document_count,
            ids_to_merge=dead_ids,
            impacted=impacted,
            document_ids=document_ids,
            documents_by_entity=documents_by_entity,
            synonym_names=synonym_names,
            repointed_synonyms=repointed,
            rename_from=rename_from,
            rename_to=rename_to,
            review_flags=flags,
        )

    def apply_entity_merge(
        self, plan: EntityMergePlan, changed_by: Author | None = None, note: str | None = None
    ) -> EntityMergeResponse:
        """
        Executes exactly what ``plan_entity_merge`` described, after writing the undo ledger.

        The order matters twice, and for the same reasons as the tag path. The ledger is written
        **before** anything changes, because what it snapshots (the spelling state and the name the
        canonical is about to lose) is exactly what the merge is about to modify. And the spellings
        already absorbed by the entities being deleted are moved to the canonical *before* the
        delete, because the synonym FK cascades and deleting first would forget the earlier
        curation.
        """
        merge_ids = self.write_entity_merge_log(plan, changed_by=changed_by, note=note)

        if plan.document_ids:
            self.link_documents_to_entity(set(plan.document_ids), plan.canonical_id)

        self.repoint_synonyms(list(plan.ids_to_merge), plan.canonical_id)

        # Only the absorbed spellings: the rename below owns the old canonical name, so the two
        # definitions of "which spelling becomes a synonym" stay in one place each.
        absorbed_names = [normalize_entity(member.name) for member in plan.impacted]
        if absorbed_names:
            self.create_synonyms(
                [
                    SynonymCommand(
                        synonym_name=name,
                        category=cast("Literal['ORG', 'PER', 'LOC']", plan.canonical_entity_type),
                        canonical_tag_id=None,
                        canonical_entity_id=plan.canonical_id,
                    )
                    for name in absorbed_names
                ]
            )

        if plan.rename_to:
            self.rename_entity(plan.canonical_id, plan.rename_to)

        entities_deleted = self.delete_entities(list(plan.ids_to_merge)) if plan.ids_to_merge else 0
        return EntityMergeResponse(
            documents_updated=len(plan.document_ids), entities_deleted=entities_deleted, merge_ids=merge_ids
        )

    def rename_entity(
        self, entity_id: int, new_name: str, *, keep_old_synonym: bool = True
    ) -> EntityRenameRecord | None:
        """
        Renames one entity and optionally anchors the old spelling as a synonym.

        The single definition of "rename a name", shared by the merge and by the rename route: the old
        spelling becomes a synonym so a future extraction still resolves to the entity, and the new
        spelling is what the catalogue shows. ``None`` when the entity does not exist. A spelling that
        only differs in case is the same name, so no synonym is written for it.

        The **spelling state is captured before the write** and returned instead of being logged here,
        because the two callers differ: the merge already wrote its own ledger row (which carries
        ``canonical_renamed_from``) and must not write a second one, while the rename route has nothing
        else to log. One implementation, one place per caller that logs it.

        A spelling another entity already carries is refused *before* the write, as
        :class:`DuplicateEntityNameError` naming that entity: ``uix_archive_entities_name_normalized``
        would raise an ``IntegrityError`` a moment later and the archivist would read a structural
        conflict that names neither the twin nor the fact that the twin is the merge case.
        """
        entity = self.db.get(ArchiveEntity, entity_id)
        if entity is None:
            return None

        trimmed = new_name.strip()
        key = normalize_entity(trimmed)
        twin = self.db.scalars(
            select(ArchiveEntity).where(
                func.lower(func.btrim(ArchiveEntity.name)) == key,
                ArchiveEntity.entity_id != entity_id,
            )
        ).one_or_none()
        if twin is not None:
            raise DuplicateEntityNameError(entity.entity_id, trimmed, twin.entity_id, twin.name)

        old_name = entity.name
        old_key = normalize_entity(old_name)
        # The pre-state the undo has to restore: whether the old spelling already pointed somewhere,
        # read before ``create_synonyms`` (an upsert) can quietly answer "nothing to do". Stored
        # spellings are normalized (``upsert_synonyms``), so the lookup is keyed the same way.
        previous_target = self.get_entity_synonym_targets([old_key], entity.entity_type).get(old_key)
        plants_synonym = keep_old_synonym and old_key != key

        entity.name = trimmed
        self.db.flush()

        if plants_synonym:
            self.create_synonyms(
                [
                    SynonymCommand(
                        synonym_name=old_name,
                        category=cast("Literal['ORG', 'PER', 'LOC']", entity.entity_type),
                        canonical_tag_id=None,
                        canonical_entity_id=entity_id,
                    )
                ]
            )
        return EntityRenameRecord(
            entity_id=entity_id,
            entity_type=entity.entity_type,
            previous_name=old_name,
            new_name=trimmed,
            synonym_created=plants_synonym and previous_target is None,
            synonym_previous_entity_id=previous_target,
        )

    def write_entity_rename_log(
        self,
        record: EntityRenameRecord,
        changed_by: Author | None = None,
        note: str | None = None,
    ) -> int:
        """
        Records one rename as a ``RENAME`` row, so the pencil on the screen has an undo.

        No absorbed entity, hence ``absorbed_*`` NULL, and the state that matters is the pair
        ``canonical_renamed_from`` / ``renamed_from_synonym_*`` — the same columns a merge's optional
        rename uses, restored by the same :meth:`_restore_canonical_name`. That is the whole reason the
        rename shares this ledger instead of growing a second one.

        ``synonym_created`` and ``document_ids`` are set explicitly rather than left to their column
        defaults: a rename links no document and absorbs no spelling, and a row that said otherwise
        would make the undo remove links nobody wrote.
        """
        stmt = (
            insert(ArchiveEntityMergeLog)
            .values(
                kind=KIND_RENAME,
                canonical_id=record.entity_id,
                canonical_name=record.new_name,
                canonical_entity_type=record.entity_type,
                absorbed_entity_id=None,
                absorbed_name=None,
                absorbed_snapshot=None,
                document_ids=[],
                created_link_ids=[],
                synonym_created=False,
                synonym_previous_entity_id=None,
                repointed_synonym_names=[],
                canonical_renamed_from=record.previous_name,
                renamed_from_synonym_created=record.synonym_created,
                renamed_from_synonym_previous_entity_id=record.synonym_previous_entity_id,
                **author_columns("changed_by", changed_by),
                note=note,
            )
            .returning(ArchiveEntityMergeLog.merge_id)
        )
        return int(self.db.scalars(stmt).one())

    def write_entity_merge_log(
        self, plan: EntityMergePlan, changed_by: Author | None = None, note: str | None = None
    ) -> list[int]:
        """
        Snapshots every entity the plan absorbs. Returns the ledger ids, oldest first.

        Reads the current rows instead of trusting the plan for the fields the dry-run does not
        carry (``entity_type``, ``created_at``) and captures the spelling state before the merge
        touches it — an undo that guesses either of those is not a lossless undo.
        """
        if not plan.ids_to_merge:
            return []

        entities = {
            entity.entity_id: entity
            for entity in self.db.scalars(
                select(ArchiveEntity).where(ArchiveEntity.entity_id.in_(plan.ids_to_merge))
            ).all()
        }
        category = plan.canonical_entity_type
        spellings_of_dead = self._entity_synonym_names_by_canonical(plan.ids_to_merge)
        mapped_spellings = self.get_entity_synonym_targets(plan.synonym_names, category)
        # Documents that already carried the canonical: the merge does not create those links, so
        # undo must not remove them either.
        already_canonical = set(
            self.get_document_ids_grouped_by_entities([plan.canonical_id]).get(plan.canonical_id, [])
        )

        renamed_from_key = normalize_entity(plan.rename_from) if plan.rename_from else None
        renamed_from_created = renamed_from_key is not None and renamed_from_key not in mapped_spellings
        renamed_from_previous = mapped_spellings.get(renamed_from_key) if renamed_from_key else None

        rows = []
        for entity_id in plan.ids_to_merge:
            entity = entities.get(entity_id)
            if entity is None:
                continue

            name = normalize_entity(entity.name)
            previous_target = mapped_spellings.get(name)
            documents = plan.documents_by_entity.get(entity_id, [])
            rows.append(
                {
                    "kind": KIND_MERGE,
                    "canonical_id": plan.canonical_id,
                    "canonical_name": plan.canonical_name,
                    "canonical_entity_type": category,
                    "absorbed_entity_id": entity.entity_id,
                    "absorbed_name": name,
                    "absorbed_snapshot": {
                        "name": entity.name,
                        "entity_type": entity.entity_type,
                        "created_at": entity.created_at.isoformat() if entity.created_at else None,
                    },
                    # Only for the restore path: the live links are the ones in the plan.
                    "document_ids": documents,
                    "created_link_ids": [doc for doc in documents if doc not in already_canonical],
                    "synonym_created": previous_target is None,
                    "synonym_previous_entity_id": previous_target,
                    "repointed_synonym_names": spellings_of_dead.get(entity_id, []),
                    "canonical_renamed_from": plan.rename_from,
                    "renamed_from_synonym_created": renamed_from_created,
                    "renamed_from_synonym_previous_entity_id": renamed_from_previous,
                    **author_columns("changed_by", changed_by),
                    "note": note,
                }
            )

        if not rows:
            return []

        stmt = insert(ArchiveEntityMergeLog).values(rows).returning(ArchiveEntityMergeLog.merge_id)
        return list(self.db.scalars(stmt).all())

    def undo_entity_merge(self, merge_id: int, undone_by: Author | None = None) -> EntityMergeLogEntryDTO:
        """
        Reverses one entry of the ledger: a merge restores the entity, a rename only the name.

        Exact by construction — the id and the row come from the snapshot, the links from the
        per-entity list, and the spelling state from what was captured before the merge. Only
        documents that still exist are re-linked: a document deleted after the merge must not make
        the undo impossible.

        A ``RENAME`` row has nothing to bring back, so it takes the branch below and reuses
        :meth:`_restore_canonical_name` — the same code that reverses the optional rename inside a
        merge. Sharing it is the point of sharing the ledger.
        """
        row = self.db.get(ArchiveEntityMergeLog, merge_id)
        if row is None:
            raise MergeLogNotFoundError(f"Registro de mesclagem {merge_id} não encontrado no ledger.")
        if row.undone_at is not None:
            raise MergeAlreadyUndoneError(
                f"A mesclagem {merge_id} já foi desfeita em {row.undone_at:%Y-%m-%d %H:%M:%S}."
            )

        if row.kind == KIND_RENAME:
            self._restore_canonical_name(row)
            row.undone_at = datetime.now(UTC)
            assign_author(row, "undone_by", undone_by)
            self.db.flush()
            return self._to_entity_merge_log_dto(row)

        snapshot = row.absorbed_snapshot or {}
        if row.absorbed_entity_id is None:
            # A ``MERGE`` row always snapshots what it absorbed, so this is a row the write cannot
            # produce. Refusing beats guessing: restoring an id read out of a null would bring back
            # the wrong entity and the ledger would record an undo that never happened.
            raise InvalidMergeError(f"O registro {merge_id} não guarda a entidade absorvida a restaurar.")
        absorbed_entity_id = row.absorbed_entity_id

        restored = ArchiveEntity(
            entity_id=absorbed_entity_id,
            name=snapshot.get("name") or row.absorbed_name,
            entity_type=snapshot.get("entity_type") or row.canonical_entity_type,
        )
        created_at = snapshot.get("created_at")
        if created_at:
            restored.created_at = datetime.fromisoformat(created_at)
        self.db.add(restored)
        self.db.flush()

        # The sequence already allocated this id once, so re-using it cannot collide with the next
        # insert (unlike a hand-written seed, which is the known pitfall with explicit ids).
        self._remove_created_entity_links(row)
        self._relink_entity_documents(absorbed_entity_id, row.document_ids or [])
        self._restore_entity_spellings(row)
        self._restore_canonical_name(row)

        row.undone_at = datetime.now(UTC)
        assign_author(row, "undone_by", undone_by)
        self.db.flush()
        return self._to_entity_merge_log_dto(row)

    def _relink_entity_documents(self, entity_id: int, document_ids: Sequence[str]) -> int:
        """Re-links the recorded documents that still exist, ignoring the ones that do not."""
        if not document_ids:
            return 0

        existing = self.db.scalars(
            select(ArchiveDocument.description_id).where(ArchiveDocument.description_id.in_(list(document_ids)))
        ).all()
        if existing:
            self.link_documents_to_entity(set(existing), entity_id)
        return len(existing)

    def _remove_created_entity_links(self, row: ArchiveEntityMergeLog) -> int:
        """
        Drops the canonical links the merge created, so undo restores the pre-merge state.

        Only the recorded subset: a document that already carried the canonical before the merge
        keeps it, and a link somebody added afterwards is not touched because it is not in the ledger.
        """
        created = row.created_link_ids or []
        if not created or row.canonical_id is None:
            return 0

        stmt = delete(ArchiveDocumentEntity).where(
            ArchiveDocumentEntity.entity_id == row.canonical_id,
            ArchiveDocumentEntity.description_id.in_(list(created)),
        )
        return cast(CursorResult, self.db.execute(stmt)).rowcount

    def _restore_entity_spellings(self, row: ArchiveEntityMergeLog) -> None:
        """
        Puts the spelling state back the way it was before the merge.

        Three cases, all captured at merge time: the spelling equal to the absorbed name was created
        by the merge (drop it), it already existed (point it back), and spellings that pointed at the
        absorbed entity were moved to the canonical (move them back). A mapping somebody changed
        later is left alone — the undo restores this merge, not the next one.
        """
        created_synonym = self.db.scalars(
            select(DomainSynonyms).where(
                DomainSynonyms.category == row.canonical_entity_type,
                DomainSynonyms.synonym_name == row.absorbed_name,
            )
        ).one_or_none()

        if created_synonym is not None:
            if row.synonym_created and created_synonym.canonical_entity_id == row.canonical_id:
                self.db.delete(created_synonym)
            elif not row.synonym_created and created_synonym.canonical_entity_id == row.canonical_id:
                created_synonym.canonical_entity_id = row.synonym_previous_entity_id
            elif row.synonym_created and created_synonym.canonical_entity_id != row.canonical_id:
                # Somebody re-pointed it after the merge: not this undo's business.
                pass

        if row.repointed_synonym_names:
            self.db.execute(
                update(DomainSynonyms)
                .where(
                    DomainSynonyms.category == row.canonical_entity_type,
                    DomainSynonyms.canonical_entity_id == row.canonical_id,
                    DomainSynonyms.synonym_name.in_(row.repointed_synonym_names),
                )
                .values(canonical_entity_id=row.absorbed_entity_id)
            )

    def _restore_canonical_name(self, row: ArchiveEntityMergeLog) -> None:
        """
        Puts back the canonical name the same merge renamed, and undoes the spelling it planted.

        Skipped silently when the canonical no longer exists (a later merge absorbed it): the
        absorbed entity still comes back, and failing here would make an unrelated undo impossible.
        """
        if not row.canonical_renamed_from or row.canonical_id is None:
            return

        canonical = self.db.get(ArchiveEntity, row.canonical_id)
        if canonical is None:
            return

        canonical.name = row.canonical_renamed_from
        self.db.flush()

        spelling = self.db.scalars(
            select(DomainSynonyms).where(
                DomainSynonyms.category == row.canonical_entity_type,
                DomainSynonyms.synonym_name == normalize_entity(row.canonical_renamed_from),
            )
        ).one_or_none()
        if spelling is None or spelling.canonical_entity_id != row.canonical_id:
            return

        if row.renamed_from_synonym_created:
            self.db.delete(spelling)
        else:
            spelling.canonical_entity_id = row.renamed_from_synonym_previous_entity_id

    def _entity_merge_log_filters(
        self,
        canonical_id: int | None,
        changed_by_name: str | None,
        include_undone: bool,
        term: str | None = None,
    ) -> list[Any]:
        """
        The filters of the ledger, including the free-text one.

        The term matches **both names** of the entry: the question that sends an archivist here is
        "where did *this* spelling go?", and which side of the merge it was is what they do not know
        yet. ``escape_like`` keeps a ``%`` in the box a character instead of "match everything".
        """
        filters: list[Any] = []
        if canonical_id is not None:
            filters.append(ArchiveEntityMergeLog.canonical_id == canonical_id)
        if changed_by_name is not None:
            filters.append(ArchiveEntityMergeLog.changed_by == changed_by_name)
        if not include_undone:
            filters.append(ArchiveEntityMergeLog.undone_at.is_(None))
        if term:
            pattern = f"%{escape_like(term)}%"
            filters.append(
                or_(
                    ArchiveEntityMergeLog.absorbed_name.ilike(pattern, escape=LIKE_ESCAPE),
                    ArchiveEntityMergeLog.canonical_name.ilike(pattern, escape=LIKE_ESCAPE),
                )
            )
        return filters

    def count_entity_merge_log(
        self,
        canonical_id: int | None = None,
        changed_by_name: str | None = None,
        include_undone: bool = True,
        term: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ArchiveEntityMergeLog)
            .where(*self._entity_merge_log_filters(canonical_id, changed_by_name, include_undone, term))
        )
        return self.db.scalar(stmt) or 0

    def list_entity_merge_log(
        self,
        canonical_id: int | None = None,
        changed_by_name: str | None = None,
        include_undone: bool = True,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EntityMergeLogEntryDTO]:
        """The audit trail: most recent first, undone entries included unless filtered out."""
        stmt = (
            select(ArchiveEntityMergeLog)
            .where(*self._entity_merge_log_filters(canonical_id, changed_by_name, include_undone, term))
            .order_by(ArchiveEntityMergeLog.merge_id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity_merge_log_dto(row) for row in self.db.scalars(stmt).all()]

    def get_entity_merge_log_entry(self, merge_id: int) -> EntityMergeLogEntryDTO | None:
        row = self.db.get(ArchiveEntityMergeLog, merge_id)
        return self._to_entity_merge_log_dto(row) if row else None

    def _to_entity_merge_log_dto(self, row: ArchiveEntityMergeLog) -> EntityMergeLogEntryDTO:
        """Maps the row to the read contract, exposing the document *count* and not the ids."""
        snapshot = row.absorbed_snapshot or {}
        return EntityMergeLogEntryDTO(
            merge_id=row.merge_id,
            kind=row.kind,
            canonical_id=row.canonical_id,
            canonical_name=row.canonical_name,
            absorbed_entity_id=row.absorbed_entity_id,
            absorbed_name=row.absorbed_name,
            # A rename row has no snapshot: the entity that changed IS the canonical, so its type is
            # the only honest answer and the screen can label the row without a second read.
            absorbed_entity_type=snapshot.get("entity_type") or row.canonical_entity_type,
            document_count=len(row.document_ids or []),
            repointed_synonym_names=list(row.repointed_synonym_names or []),
            synonym_created=row.synonym_created,
            canonical_renamed_from=row.canonical_renamed_from,
            changed_by=row.changed_by,
            changed_at=row.changed_at,
            note=row.note,
            undone_at=row.undone_at,
            undone_by=row.undone_by,
        )

    # --- Analytical Queries and Maintenance ---

    def search_entities(self, term: str, limit: int) -> Sequence[EntityRelevance]:
        """
        Entities whose name contains ``term``, the most used first.

        The same read view as the relevance screen, because the curator's question is the same —
        "which of these 3.808 names is the one I mean?" — and the count is what separates two
        entities that differ by an abbreviation. ``ILIKE '%term%'`` is served by the trigram index
        on the name, and the wildcards typed in the box are escaped so a ``%`` cannot match
        everything.
        """
        needle = term.strip()
        if not needle:
            return []

        pattern = f"%{escape_like(needle)}%"
        # The count is restricted to the names that match, so the aggregate does not walk the whole
        # link table on every keystroke of a type-ahead.
        counts = (
            select(ArchiveDocumentEntity.entity_id, func.count().label("total_usage"))
            .join(ArchiveEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)
            .where(ArchiveEntity.name.ilike(pattern, escape=LIKE_ESCAPE))
            .group_by(ArchiveDocumentEntity.entity_id)
            .subquery()
        )
        stmt = (
            select(
                ArchiveEntity.entity_id,
                ArchiveEntity.name,
                ArchiveEntity.entity_type,
                func.coalesce(counts.c.total_usage, 0).label("total_usage"),
            )
            .outerjoin(counts, counts.c.entity_id == ArchiveEntity.entity_id)
            .where(ArchiveEntity.name.ilike(pattern, escape=LIKE_ESCAPE))
            .order_by(func.coalesce(counts.c.total_usage, 0).desc(), ArchiveEntity.name)
            .limit(limit)
        )
        return [EntityRelevance.model_validate(row) for row in self.db.execute(stmt).mappings().all()]

    def get_relevance_count(
        self, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> Sequence[EntityRelevance]:
        """Fetches the most referenced entities in documents."""
        stmt = select(
            ArchiveEntity.entity_id,
            ArchiveEntity.name,
            ArchiveEntity.entity_type,
            func.count(ArchiveDocumentEntity.description_id).label("total_usage"),
        ).join(ArchiveDocumentEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)

        if entity_type:
            stmt = stmt.where(ArchiveEntity.entity_type == entity_type)

        stmt = stmt.group_by(ArchiveEntity.entity_id).order_by(desc("total_usage")).limit(limit)
        return [EntityRelevance.model_validate(row) for row in self.db.execute(stmt).all()]

    def purge_orphan_entities(self) -> int:
        """Finds and deletes entities that do not have any linked document."""
        stmt_orphans = (
            select(ArchiveEntity.entity_id)
            .outerjoin(ArchiveDocumentEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)
            .where(ArchiveDocumentEntity.description_id.is_(None))
        )

        orphans = self.db.scalars(stmt_orphans).all()

        if not orphans:
            return 0

        result = self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id.in_(orphans)))
        return cast(CursorResult, result).rowcount

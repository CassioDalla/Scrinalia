from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, delete, desc, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from memoria_curitibana.domains.archive.domain.normalization import (
    LIKE_ESCAPE,
    escape_like,
    normalize_entity,
    normalize_stopword,
    normalize_synonym,
)
from memoria_curitibana.domains.archive.exceptions import (
    ConflictResolutionAlreadyUndoneError,
    ConflictResolutionNotFoundError,
    InvalidParam,
    UnresolvableConflictError,
)
from memoria_curitibana.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveConflictResolutionLog,
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveReviewStatus,
    ArchiveTag,
    DomainNerExclusion,
    DomainStopwords,
    DomainSynonyms,
    StopwordsScope,
)
from memoria_curitibana.domains.archive.schemas.command_schema import EntityLinkCommand, SynonymCommand
from memoria_curitibana.domains.archive.schemas.entity_schema import (
    ArchiveEntityDTO,
    ConflictBanKind,
    ConflictDecider,
    ConflictResolutionData,
    ConflictResolutionLogEntry,
    ConflictResolutionPlan,
    ConflictWinner,
    CrossDomainConflict,
    CrossDomainConflictPage,
    EntityIdentity,
    EntityPairSimilarity,
    EntityRelevance,
    EntitySimilarity,
    JudgedConflict,
    JudgedConflictPage,
    NerExclusion,
    NerExclusionSource,
    NerSynonymRule,
)


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
        case for trigram extraction, so ``similarity('Batel', 'batel') = 1`` and at **any** threshold
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
            .order_by(desc("similarity"))
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

    def page_cross_domain_conflicts(
        self,
        threshold: float = 0.85,
        pair_kind: Literal["all", "exact_name", "near_duplicate"] = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> CrossDomainConflictPage:
        """
        One page of the live scan, annotated with what has already been decided about each pair.

        The scan itself is not paginable in SQL — the trigram join has to produce and sort the whole
        candidate set before a page means anything — so the page is sliced after the scan. What the
        API returns is bounded by ``limit``; what it reads is not. That is the honest trade, and it
        is why the counts below are over the **whole** filtered set rather than the page: the
        screen's "122 grafias diferentes / 5 050 nomes idênticos" cannot come from a page.

        ``pair_kind`` is the lever that makes the list usable. ``exact_name`` is a structural
        question (the same spelling on both axes) and ``near_duplicate`` is a spelling question; the
        default is ``all`` so nothing is hidden, and the screen chooses which population to open.

        The parameter is not called ``scope`` because Litestar reserves that name for the ASGI scope:
        a handler parameter called ``scope`` silently receives the raw request instead of the query
        string. The stopwords route was bitten by the same trap and renamed its key to ``axis``.
        """
        verdicts = self._judge_verdicts()
        resolutions = self._active_resolutions()

        annotated: list[CrossDomainConflict] = []
        for conflict in self.get_cross_domain_conflicts(threshold):
            pair = (conflict.tag_id, conflict.entity_id)
            verdict = verdicts.get(pair, {})
            resolution = resolutions.get(pair)
            annotated.append(
                conflict.model_copy(
                    update={
                        **verdict,
                        "resolution_id": resolution[0] if resolution else None,
                        "resolution_winner": resolution[1] if resolution else None,
                        "resolution_source": resolution[2] if resolution else None,
                    }
                )
            )

        if pair_kind == "exact_name":
            filtered = [row for row in annotated if row.pair_kind == "EXACT_NAME"]
        elif pair_kind == "near_duplicate":
            filtered = [row for row in annotated if row.pair_kind == "NEAR_DUPLICATE"]
        else:
            filtered = annotated

        return CrossDomainConflictPage(
            total=len(filtered),
            limit=limit,
            offset=offset,
            items=filtered[offset : offset + limit],
            exact_name_count=sum(1 for row in filtered if row.pair_kind == "EXACT_NAME"),
            near_duplicate_count=sum(1 for row in filtered if row.pair_kind == "NEAR_DUPLICATE"),
            judged_count=sum(1 for row in filtered if row.judge_winner is not None or row.resolution_id is not None),
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

    def plan_conflict_resolution(self, tag_id: int, entity_id: int, similarity: float = 0.0) -> ConflictResolutionPlan:
        """
        Everything a resolution would change, computed without writing anything.

        Single definition of the operation: the preview returns this plan and
        :meth:`apply_conflict_resolution` executes it, so the dry run cannot promise a different
        number from the write — the same rule ``TagRepository.plan_merge`` follows.

        Both verdicts are computed, because the archivist's question is comparative. The three facts
        that decide it are: how many documents follow the loser to the winner, how many of those
        already carry the winner (so the transfer changes nothing for them), and whether the ban the
        resolution would plant is already in place.
        """
        tag = self.db.get(ArchiveTag, tag_id)
        entity = self.db.get(ArchiveEntity, entity_id)

        tag_docs = self._document_ids_by_tag(tag_id) if tag is not None else []
        entity_docs = self._document_ids_by_entity(entity_id) if entity is not None else []

        tag_linked = set(tag_docs)
        entity_linked = set(entity_docs)

        # The judge's verdict, so the preview can show what has already been decided.
        verdict = self._judge_verdicts().get((tag_id, entity_id), {})
        already_resolved = (tag_id, entity_id) in self._active_resolutions()

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
        decided_by: str | None = None,
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
            transferred_document_ids=sorted(loser_docs),
            created_link_ids=created_link_ids,
            ban_kind=ban_kind,
            ban_term=ban_term,
            ban_created=not ban_exists,
            decided_by=decided_by,
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

    def undo_conflict_resolution(self, resolution_id: int, undone_by: str | None = None) -> ConflictResolutionLogEntry:
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

        self._remove_created_conflict_links(row)
        self._restore_conflict_links(row)
        self._lift_conflict_ban(row)

        row.undone_at = datetime.now(UTC)
        row.undone_by = undone_by
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
    ) -> int:
        """
        Plan and apply in one call, through the ledger.

        Kept as the single entry point for callers that have no reason to inspect the impact first
        (the judge worker, which has already made the decision), so no path can write a resolution
        that leaves no trace. The API uses the two halves separately, because the archivist is
        entitled to see the numbers before the write.
        """
        plan = self.plan_conflict_resolution(tag_id, entity_id)
        data = self.apply_conflict_resolution(plan, winner, source=source, decided_by=source)
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
        # "Curitiba" and "curitiba" resolve to the same canonical entity.
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

    def get_document_ids_by_entities(self, entity_ids: list[int]) -> Sequence[str]:
        stmt = select(ArchiveDocumentEntity.description_id).where(ArchiveDocumentEntity.entity_id.in_(entity_ids))
        return self.db.scalars(stmt).all()

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

        Upsert, not ``on_conflict_do_nothing``: when a canonical entity is absorbed into
        another one, a spelling that already had a mapping has to *move*. Keeping the old
        target made a re-merge look successful while changing nothing, and left the extraction
        pointing at an entity that no longer exists. Same defect and same fix as the tag path.
        """
        if not synonyms_data:
            return

        rows = [
            {
                "synonym_name": normalize_synonym(item.synonym_name),
                "category": item.category,
                "canonical_tag_id": item.canonical_tag_id,
                "canonical_entity_id": item.canonical_entity_id,
            }
            for item in synonyms_data
        ]
        stmt = insert(DomainSynonyms).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["synonym_name", "category"],
            set_={
                "canonical_tag_id": stmt.excluded.canonical_tag_id,
                "canonical_entity_id": stmt.excluded.canonical_entity_id,
            },
        )
        self.db.execute(stmt)

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

    def update_entity_name(self, entity_id: int, new_name: str) -> None:
        entity = self.db.query(ArchiveEntity).filter(ArchiveEntity.entity_id == entity_id).first()
        if entity:
            entity.name = new_name

    def delete_entities_by_names(self, names: list[str]) -> int:
        """Deletes entities from the collection by searching for a list of exact names."""
        clean_names = [normalize_entity(n) for n in names]

        deleted_rows = (
            self.db.query(ArchiveEntity)
            .filter(func.lower(ArchiveEntity.name).in_(clean_names))
            .delete(synchronize_session=False)
        )

        return deleted_rows

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

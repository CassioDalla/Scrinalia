# api/controllers/taxonomy_controller.py
from collections.abc import Sequence
from typing import Literal

import anyio
import anyio.to_process
from litestar import Controller, delete, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import provide_current_user, provide_entity_service, provide_tag_service
from scrinalia.api.schemas.taxonomy import (
    ConflictBatchRequest,
    ConflictBatchResponse,
    ConflictPreviewRequest,
    ConflictResolutionRequest,
    ConflictResolutionResponse,
    EntityMergePreviewRequest,
    EntityMergeRequest,
    EntityRenameRequest,
    MacroCategoryCreateRequest,
    MacroCategoryUpdateRequest,
    MergeBatchRequest,
    MergePreviewRequest,
    MergeProposalDecisionRequest,
    MergeRequest,
    MergeSuggestionRequest,
    NerExclusionRequest,
    ReclassifyEntityRequest,
    StopwordCreateRequest,
    StopwordMatchRequest,
    StopwordRemovalRequest,
    StopwordsRequest,
    SubjectExclusionRemovalRequest,
    SubjectExclusionRequest,
    SuggestMacroRequest,
    TagCurationRequest,
)
from scrinalia.api.security import Access, AuthenticatedUser
from scrinalia.domains.archive.models.enums import StopwordsScope, TagCatalogState
from scrinalia.domains.archive.schemas import (
    ArchiveMacroCategoryEntityDTO,
    BatchMergeResponse,
    ConflictResolutionLogListResponse,
    ConflictResolutionPlan,
    CreateMacroCategoryCommand,
    CrossDomainConflictPage,
    EntityKind,
    JudgedConflictPage,
    MergeBatchCommand,
    MergeEntityCommand,
    MergeEntityPreviewCommand,
    MergeLogListResponse,
    MergePreviewCommand,
    MergePreviewResponse,
    MergeSuggestionRunResponse,
    MergeTagsCommand,
    ResolveConflictBatchCommand,
    ResolveConflictCommand,
    RouteMessageCode,
    StopwordDTO,
    StopwordPurgeLogListResponse,
    StopwordPurgePreview,
    SubjectExclusionSuggestionResponse,
    TagCatalogResponse,
    TagCurationCommand,
    TagCurationResult,
    TagMergeDecisionCommand,
    TagMergeProposalListResponse,
    TagSearchResult,
    UpdateMacroCategoryCommand,
)
from scrinalia.domains.archive.schemas.entity_schema import (
    EntityDeleteResponse,
    EntityMergeLogListResponse,
    EntityMergePreviewResponse,
    EntityMergeResponse,
    EntityMergeUndoResponse,
    EntityReclassifyResponse,
    EntityRelevance,
    EntityRelevanceResponse,
    EntityRenameResponse,
    EntitySimilarityResponse,
    NerExclusion,
    NerExclusionBanResponse,
    NerExclusionRemovalResponse,
    NerPurgeLogListResponse,
    NerPurgePreview,
    NerPurgeResponse,
    NerPurgeUndoResponse,
    OrphanEntityPurgeResponse,
)
from scrinalia.domains.archive.schemas.tag_schema import (
    MacroCategoriesSuggestionResponse,
    MergeResponse,
    StopwordBanResponse,
    StopwordMatchResponse,
    StopwordPurgeResponse,
    StopwordPurgeUndoResponse,
    StopwordRemovalResponse,
    SubjectExclusionBanResponse,
    SubjectExclusionPlan,
    SubjectExclusionRemovalResponse,
    TagMergeProposalDecisionResponse,
    TagMergeUndoResponse,
    TagPairSimilarity,
    TagRelevanceResponse,
    TagSimilarity,
)
from scrinalia.domains.archive.services.entity_service import EntityService
from scrinalia.domains.archive.services.tag_service import TagService


class TaxonomyController(Controller):
    path = "/api/v1/taxonomy"
    tags = ["Taxonomy"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "current_user": Provide(provide_current_user, sync_to_thread=False),
        "tag_service": Provide(provide_tag_service, sync_to_thread=False),
        "entity_service": Provide(provide_entity_service, sync_to_thread=False),
    }

    @get("/tags", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def search_tags(
        self,
        tag_service: NamedDependency[TagService],
        term: FromQuery[str],
        limit: FromQuery[int] = 20,
    ) -> list[TagSearchResult]:
        """
        Tags matching what the curator is typing, heaviest first.

        Exists because the dossier used to ask for the **id** of a tag in a text box, which is not
        a thing an archivist knows. Two characters is the floor; anything shorter answers an empty
        list rather than an arbitrary slice of the catalogue.
        """
        return tag_service.search_tags(term, limit)

    @patch("/tags/{tag_id:int}", opt={"access": Access.CURATE}, sync_to_thread=True)
    def curate_tag(
        self,
        tag_service: NamedDependency[TagService],
        tag_id: FromPath[int],
        data: TagCurationRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> TagCurationResult:
        """
        Moves one tag into a subject drawer, or declares that it is not a subject at all.

        A global decision about the vocabulary, not a local edit: it changes the badge of every
        description that carries the tag, and the response says as much by being the tag itself.
        """
        return tag_service.curate_tag_macro_category(
            tag_id, TagCurationCommand(**data.model_dump(), changed_by=current_user.author)
        )

    @get("/tags/catalog", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_tag_catalog(
        self,
        tag_service: NamedDependency[TagService],
        # NOT ``state``: Litestar reserves that parameter name for the ASGI state, and a handler that
        # uses it silently receives the request's ``State`` instead of the query value. ``scope`` was
        # the first of these (the stopwords route renamed its key to ``axis``) and the reserved-name
        # failure is a 500 at app construction, which is how this one was found.
        subject_state: FromQuery[TagCatalogState] = TagCatalogState.ALL,
        macro_category_id: FromQuery[int | None] = None,
        term: FromQuery[str | None] = None,
        limit: FromQuery[int] = 25,
        offset: FromQuery[int] = 0,
    ) -> TagCatalogResponse:
        """
        One page of the tag catalogue, filtered by the state of the subject decision.

        The read the home screen's cards land on, and one the type-ahead cannot answer: a list of the
        tags **nobody has decided about** is a filter over the catalogue, while the relevance lists
        are a top-N by weight with no notion of state at all — the card promised 76 tags and the
        screen it opened could not mark which rows they were.

        ``subject_state`` and ``macro_category_id`` are different questions and the caller may ask
        both: "decided how" and "in which drawer".
        """
        return tag_service.list_catalog(
            state=subject_state, macro_category_id=macro_category_id, term=term, limit=limit, offset=offset
        )

    @get("/tags/relevance/{method:str}", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_tag_relevance(
        self,
        tag_service: NamedDependency[TagService],
        method: FromPath[Literal["tfidf", "count"]],
        limit: FromQuery[int] = 30,
    ) -> TagRelevanceResponse:

        if method == "tfidf":
            results = tag_service.get_tag_relevance_tfidf(limit)
        else:
            results = tag_service.get_tag_relevance_count(limit)

        return TagRelevanceResponse.from_payload(list(results))

    @get("/tags/similar", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_similar_tags(
        self,
        tag_service: NamedDependency[TagService],
        target: FromQuery[str | None] = None,
        threshold: FromQuery[float] = 0.4,
    ) -> list[TagSimilarity] | list[TagPairSimilarity]:

        if not target:
            results = tag_service.find_all_similar_tag_pairs(threshold)
            return list(results)

        results = tag_service.find_similar_tags(target, threshold)
        return list(results)

    @post("/tags/merge", opt={"access": Access.CURATE}, sync_to_thread=True)
    def merge_tags(
        self,
        tag_service: NamedDependency[TagService],
        data: MergeRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> MergeResponse:
        response = tag_service.merge(
            MergeTagsCommand(
                canonical_id=data.canonical_id,
                ids_to_merge=data.ids_to_merge,
                changed_by=current_user.author,
            )
        )

        return response

    @post("/tags/merge/preview", opt={"access": Access.AUTHENTICATED}, status_code=200, sync_to_thread=True)
    def preview_tag_merge(
        self,
        tag_service: NamedDependency[TagService],
        data: MergePreviewRequest,
    ) -> MergePreviewResponse:
        """
        Dry-run of a merge: how many documents change, what is lost and what to review.

        Read-only. The archivist approves with the number in hand, never on the hope that the
        cluster the routine proposed is harmless — measurement showed it often is not
        (``rua 24 de maio`` <- ``rua 13 de maio``).
        """
        return tag_service.preview_merge(
            MergePreviewCommand(
                proposal_id=data.proposal_id,
                canonical_id=data.canonical_id,
                ids_to_merge=data.ids_to_merge,
            )
        )

    @post("/tags/merge-proposals/suggest", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def suggest_tag_merges(
        self,
        tag_service: NamedDependency[TagService],
        data: MergeSuggestionRequest,
    ) -> MergeSuggestionRunResponse:
        """
        Scans the tag catalog, groups probable duplicates and registers them as proposals.

        Nothing is merged and no decision is taken: the routine only ever writes ``SUGGESTED``
        and never touches a cluster a human already approved or rejected.
        """
        return tag_service.suggest_merges(threshold=data.threshold, limit=data.limit)

    @get("/tags/merge-proposals", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_tag_merge_proposals(
        self,
        tag_service: NamedDependency[TagService],
        status: FromQuery[Literal["SUGGESTED", "APPROVED", "REJECTED", "APPLIED"] | None] = None,
        reason: FromQuery[Literal["TRIGRAM", "PLURAL", "MIXED"] | None] = None,
        min_documents: FromQuery[int] = 0,
        flagged_only: FromQuery[bool] = False,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> TagMergeProposalListResponse:
        """
        One page of proposals, pending work first, with the total for the same filters.

        Pagination is not a nicety here: the real collection produced hundreds of clusters,
        and before this catalog the route returned the first fifty without saying how many
        existed.
        """
        return tag_service.list_merge_proposals(
            status=status,
            reason=reason,
            min_documents=min_documents,
            flagged_only=flagged_only,
            limit=limit,
            offset=offset,
        )

    @patch("/tags/merge-proposals/{proposal_id:int}", opt={"access": Access.CURATE}, sync_to_thread=True)
    def decide_tag_merge_proposal(
        self,
        tag_service: NamedDependency[TagService],
        proposal_id: FromPath[int],
        data: MergeProposalDecisionRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> TagMergeProposalDecisionResponse:
        """Approves or rejects a proposed cluster. Approval records intent, it does not merge."""
        proposal = tag_service.decide_merge_proposal(
            proposal_id,
            TagMergeDecisionCommand(status=data.status, decided_by=current_user.author, note=data.note),
        )
        return TagMergeProposalDecisionResponse(
            code=RouteMessageCode.TAG_MERGE_PROPOSAL_DECIDED,
            message="Decisão registrada. A mesclagem só será aplicada quando o lote for executado.",
            data=proposal,
        )

    @post("/tags/merge/batch", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def apply_tag_merge_batch(
        self,
        tag_service: NamedDependency[TagService],
        data: MergeBatchRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> BatchMergeResponse:
        """
        Applies a batch of proposals, one savepoint per cluster, and reports each outcome.

        The write is logged in the ledger, so every cluster applied here can be undone
        individually through ``DELETE /tags/merge-log/{merge_id}``.
        """
        return tag_service.merge_batch(
            MergeBatchCommand(proposal_ids=data.proposal_ids, changed_by=current_user.author, note=data.note)
        )

    @get("/tags/merge-log", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_tag_merge_log(
        self,
        tag_service: NamedDependency[TagService],
        canonical_id: FromQuery[int | None] = None,
        changed_by: FromQuery[str | None] = None,
        include_undone: FromQuery[bool] = True,
        # ``q`` and not ``term``: the collection search already owns ``term`` for its own meaning, and
        # this one is a filter *inside* a ledger. The front reads the same name it sends.
        q: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> MergeLogListResponse:
        """
        The audit trail of the merges: what was merged, by whom, and what was undone.

        ``q`` matches both sides of the entry — the absorbed and the canonical name — because the
        archivist asking "where did this spelling go?" does not know which side it was on.
        """
        return tag_service.list_merge_log(
            canonical_id=canonical_id,
            changed_by_name=changed_by,
            include_undone=include_undone,
            term=q,
            limit=limit,
            offset=offset,
        )

    @delete("/tags/merge-log/{merge_id:int}", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def undo_tag_merge(
        self,
        tag_service: NamedDependency[TagService],
        merge_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> TagMergeUndoResponse:
        """
        Undoes one merge from the ledger: the tag, its links, its classification and its
        spellings come back exactly as they were.
        """
        entry = tag_service.undo_merge(merge_id, undone_by=current_user.author)
        return TagMergeUndoResponse(
            code=RouteMessageCode.TAG_MERGE_UNDONE,
            message=f"Mesclagem desfeita: a tag '{entry.absorbed_name}' foi restaurada.",
            data=entry,
        )

    @get("/tags/stopwords", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_stopwords(
        self,
        tag_service: NamedDependency[TagService],
        # The query key is ``axis``, not ``scope``: Litestar reserves the parameter name ``scope``
        # for the ASGI scope, and a handler that used it received the raw request instead of the
        # query value. A route test caught that, not the type checker.
        axis: FromQuery[StopwordsScope | None] = None,
    ) -> list[StopwordDTO]:
        """
        The banned terms, with the axis each was banned from.

        The scope is part of the payload on purpose: ``TAG`` feeds the subject purge while ``ENTITY``
        keeps a term out of the NER extraction, and a screen that showed them as one list would make
        the two mechanisms look like the same decision.
        """
        return tag_service.list_stopwords(axis)

    @post("/tags/stopwords", opt={"access": Access.CURATE}, status_code=201, sync_to_thread=True)
    def create_stopwords(
        self,
        tag_service: NamedDependency[TagService],
        data: StopwordCreateRequest,
    ) -> StopwordBanResponse:
        """Bans terms. Banning does not delete anything: the purge is a separate, explicit step."""
        created = tag_service.save_new_stopwords(data.words, data.scope, match_mode=data.match_mode)
        return StopwordBanResponse(
            code=RouteMessageCode.TAG_STOPWORDS_BANNED,
            message=f"{created} stopword(s) registrada(s) no eixo {data.scope}.",
            created=created,
        )

    @patch("/tags/stopwords", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def update_stopword_match(
        self,
        tag_service: NamedDependency[TagService],
        data: StopwordMatchRequest,
    ) -> StopwordMatchResponse:
        """
        Changes how the given bans match, keeping their axis and who planted them.

        A separate route from the ban on purpose: re-banning would take ownership of the row and
        overwrite the ``source`` a conflict or the "not a subject" screen recorded (#160).
        """
        updated = tag_service.set_stopword_match(data.words, data.match_mode)
        return StopwordMatchResponse(
            code=RouteMessageCode.TAG_STOPWORDS_MATCH_UPDATED,
            message=f"{updated} stopword(s) passam a casar por {data.match_mode}.",
            updated=updated,
        )

    @delete("/tags/stopwords", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def remove_stopwords(
        self,
        tag_service: NamedDependency[TagService],
        data: StopwordRemovalRequest,
    ) -> StopwordRemovalResponse:
        """Un-bans terms. The purge keeps a ledger, so this is no longer the only way back."""
        removed = tag_service.remove_stopwords(data.words, data.scope)
        return StopwordRemovalResponse(
            code=RouteMessageCode.TAG_STOPWORDS_REMOVED,
            message=f"{removed} stopword(s) removida(s).",
            removed=removed,
        )

    @post("/tags/stopwords/purge/preview", opt={"access": Access.AUTHENTICATED}, status_code=200, sync_to_thread=True)
    def preview_stopword_purge(self, tag_service: NamedDependency[TagService]) -> StopwordPurgePreview:
        """
        The dry run of the purge: the tags that would die, and the ledger that can bring them back.

        It lists the tags the purge would delete, with how many descriptions carry each and which
        drawer dies with it, so the screen can show the loss before it happens. The list is the plan
        the purge itself consumes, so the preview and the write cannot disagree.
        """
        return tag_service.preview_stopword_purge()

    @post("/tags/stopwords/purge", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def purge_stopwords(
        self,
        tag_service: NamedDependency[TagService],
        data: StopwordsRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> StopwordPurgeResponse:
        """
        Deletes every tag whose name is a banned term, after logging each one in the ledger.

        ``words`` is optional and, when sent, is registered before the purge, so a client may ban and
        purge in one call. The screen sends an **empty body**: it purges with the list it already
        showed in the preview, so the numbers the archivist approved are the numbers that die. The
        response carries the ``purge_ids`` the screen needs to offer the undo — without them the
        archivist would have to find the row in the ledger to reverse the click they just made.
        """
        if data.words:
            tag_service.save_new_stopwords(data.words)

        result = tag_service.purge_stopwords(current_user.author)
        return StopwordPurgeResponse(
            code=RouteMessageCode.TAG_STOPWORD_PURGE_DONE,
            message="Limpeza concluída com sucesso.",
            tags_deleted=result.tags_deleted,
            purge_ids=result.purge_ids,
        )

    @get("/tags/stopwords/purge-log", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_stopword_purge_log(
        self,
        tag_service: NamedDependency[TagService],
        include_undone: FromQuery[bool] = True,
        # ``q`` and not ``term``: the collection search already owns ``term`` for its own meaning,
        # and this one is a filter *inside* a ledger. The front reads the same name it sends.
        q: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> StopwordPurgeLogListResponse:
        """
        The audit trail of the purges: what died, by whom, and what was restored.

        ``q`` matches the purged tag's name — the question that sends an archivist here is "where
        did this spelling go?", and the answer is a row that can be put back.
        """
        return tag_service.list_stopword_purge_log(include_undone=include_undone, term=q, limit=limit, offset=offset)

    @delete(
        "/tags/stopwords/purge-log/{purge_id:int}", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True
    )
    def undo_stopword_purge(
        self,
        tag_service: NamedDependency[TagService],
        purge_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> StopwordPurgeUndoResponse:
        """
        Undoes one purge from the ledger: the tag, its links and its spellings come back.

        The second attempt is **409** and an unknown id is **404**; the ledger entry is never
        deleted, so the history of "this was purged, then restored" survives. The ban stays: the
        term is still a stopword, and the next purge lists it again.
        """
        entry = tag_service.undo_stopword_purge(purge_id, undone_by=current_user.author)
        return StopwordPurgeUndoResponse(
            code=RouteMessageCode.TAG_STOPWORD_PURGE_UNDONE,
            message=f"Purga desfeita: a tag '{entry.purged_name}' foi restaurada.",
            data=entry,
        )

    # ``AUTHENTICATED`` and not ``CURATE``: the route computes candidates and writes nothing, and
    # the permission is about what a request can *change* — the route that applies a suggestion has
    # its own permission. The clustering is expensive (BERTopic, seconds of CPU) and that is the
    # accepted trade, the same one the previews make; it is pinned in ``READ_ONLY_POSTS``.
    @post("/tags/suggest-macro", opt={"access": Access.AUTHENTICATED})
    async def suggest_macro_categories(
        self, tag_service: NamedDependency[TagService], data: SuggestMacroRequest
    ) -> MacroCategoriesSuggestionResponse:

        texts_to_analyze = tag_service.get_text_to_suggest_macro_category(
            source_type=data.source_type, columns_to_extract=data.columns_to_extract
        )

        # Imported here because the suggestion worker reaches the clustering registry,
        # which is what drags BERTopic (about ten seconds) into the process. Only this
        # route needs it, so the API must not pay for it at import time. The guard below
        # reads the worker's own floor, so the API cannot drift from the engine.
        from scrinalia.domains.archive.workers.worker_suggest_macro_category import (
            MIN_TEXTS_TO_CLUSTER,
            run_suggestion_engine,
        )

        if not texts_to_analyze or len(texts_to_analyze) < MIN_TEXTS_TO_CLUSTER:
            return MacroCategoriesSuggestionResponse(
                total_suggestions=0,
                categories=[],
                code=RouteMessageCode.MACRO_CLUSTERING_INSUFFICIENT_TEXTS,
                message="⚠️ Textos insuficientes para formar agrupamentos semânticos.",
            )

        # anyio.to_process.run_sync receives the function and then its positional arguments.
        results = await anyio.to_process.run_sync(
            run_suggestion_engine,
            texts_to_analyze,  # We pass source_type positionally
        )

        return results

    # ==========================================
    # ROUTES: SUBJECT EXCLUSIONS (the term is not an "about")
    # ==========================================

    @get("/tags/subject-exclusions", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_subject_exclusions(self, tag_service: NamedDependency[TagService]) -> list[str]:
        """Lists the terms the curation decided are not a subject."""
        return tag_service.list_subject_exclusions()

    @get("/tags/subject-exclusions/suggestions", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def suggest_subject_exclusions(
        self,
        tag_service: NamedDependency[TagService],
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
        include_excluded: FromQuery[bool] = False,
    ) -> SubjectExclusionSuggestionResponse:
        """
        The terms the deterministic guard already refuses, computed — not judged by a model.

        The guard has always skipped these terms inside ``worker_macro_category``, and until now the
        archivist could not see a single one of them: 1.489 of the 8.155 real tags, including
        ``local não identificado`` (310 documents), 689 streets and 707 bare numbers. Each candidate
        carries its evidence — weight, whether the term is a place (the entity axis owns it), whether
        the same spelling is also a named entity, the drawer that would block it and whether its
        spelling is already banned — and the route deliberately proposes **nothing** for the semantic
        half (``pessoas``, ``vista aérea``), where the measurement says the model answers confidently
        and wrongly.
        """
        return tag_service.suggest_subject_exclusions(limit=limit, offset=offset, include_excluded=include_excluded)

    @post(
        "/tags/subject-exclusions/preview", opt={"access": Access.AUTHENTICATED}, status_code=200, sync_to_thread=True
    )
    def preview_subject_exclusions(
        self, tag_service: NamedDependency[TagService], data: SubjectExclusionRequest
    ) -> SubjectExclusionPlan:
        """
        What confirming these terms would do, without writing anything.

        ``applicable`` is what the write will record — the exclusion and the ``TAG``-scoped ban — and
        ``blocked`` is what it refuses, each with the drawer in the way. A term whose tag already sits
        in a subject drawer is a subject question already answered, and the write that settles a *tag*
        is the tag catalogue's ``PATCH``; asking for the opposite here would destroy a human verdict
        with a statement about a term.
        """
        return tag_service.plan_subject_exclusions(data.words)

    @post("/tags/subject-exclusions", opt={"access": Access.CURATE}, status_code=201, sync_to_thread=True)
    def create_subject_exclusions(
        self, tag_service: NamedDependency[TagService], data: SubjectExclusionRequest
    ) -> SubjectExclusionBanResponse:
        """
        Records that a term is not a subject and bans its spelling from becoming a tag again.

        Nothing is deleted: the term stays a tag of the collection and stays reachable by search until
        the archivist purges it, which is a separate act behind its own preview and ledger. The ban
        only stops the next ingestion from recreating the term — and it is written at ``TAG`` scope,
        so the NER keeps extracting the name as an entity. A term whose tag sits in a drawer is
        refused and reported in ``blocked`` instead of silently un-filing it.
        """
        result = tag_service.exclude_terms_from_subjects(data.words, reason=data.reason, source=data.source)
        if result.blocked and result.created == 0:
            return SubjectExclusionBanResponse(
                code=RouteMessageCode.SUBJECT_EXCLUSIONS_BLOCKED,
                message=(
                    "Nenhum termo foi marcado: as tags abaixo já estão numa categoria de assunto. "
                    "Tire-as da categoria no catálogo de tags antes de declará-las não-assunto."
                ),
                created=result.created,
                banned=result.banned,
                blocked=result.blocked,
            )
        if result.blocked:
            return SubjectExclusionBanResponse(
                code=RouteMessageCode.SUBJECT_EXCLUSIONS_PARTIAL,
                message=(
                    f"{result.created} termo(s) marcados como não-assunto e banidos de voltar; "
                    f"{len(result.blocked)} recusado(s) por já estarem numa categoria de assunto."
                ),
                created=result.created,
                banned=result.banned,
                blocked=result.blocked,
            )
        return SubjectExclusionBanResponse(
            code=RouteMessageCode.SUBJECT_EXCLUSIONS_ADDED,
            message=(
                "Termos marcados como não-assunto: o classificador de assuntos vai ignorá-los e as "
                "grafias não voltam a virar tag."
            ),
            created=result.created,
            banned=result.banned,
            blocked=result.blocked,
        )

    @delete("/tags/subject-exclusions", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def remove_subject_exclusions(
        self, tag_service: NamedDependency[TagService], data: SubjectExclusionRemovalRequest
    ) -> SubjectExclusionRemovalResponse:
        """
        Undoes the decision: the terms return to the classification queue and the ban this write
        planted leaves with them.

        The lift is exact — only a ban the exclusion itself created — so a spelling a person banned
        on the Stopwords screen, or one a conflict resolution planted first, survives.
        """
        result = tag_service.remove_subject_exclusions(data.words)
        return SubjectExclusionRemovalResponse(
            code=RouteMessageCode.SUBJECT_EXCLUSIONS_REMOVED,
            message="Exclusões removidas: o classificador voltará a considerar esses termos.",
            removed=result.removed,
            unbanned=result.unbanned,
        )

    @get("/macro-categories", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_macro_categories(
        self,
        tag_service: NamedDependency[TagService],
        only_active: FromQuery[bool] = False,
    ) -> list[ArchiveMacroCategoryEntityDTO]:
        """Lists the official macro categories (the subject axis of the collection)."""
        return tag_service.list_macro_categories(only_active=only_active)

    @post("/macro-categories", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def create_macro_category(
        self,
        tag_service: NamedDependency[TagService],
        data: MacroCategoryCreateRequest,
    ) -> ArchiveMacroCategoryEntityDTO:
        """Registers a macro category. A duplicate name is rejected with 409."""
        return tag_service.create_macro_category(
            CreateMacroCategoryCommand(
                name=data.name, description=data.description, classifier_label=data.classifier_label
            )
        )

    @patch("/macro-categories/{category_id:int}", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def update_macro_category(
        self,
        tag_service: NamedDependency[TagService],
        category_id: FromPath[int],
        data: MacroCategoryUpdateRequest,
    ) -> ArchiveMacroCategoryEntityDTO:
        """Renames, re-describes, rewrites the classifier label or (de)activates a macro category."""
        command = UpdateMacroCategoryCommand(**data.model_dump(exclude_unset=True))
        return tag_service.update_macro_category(category_id, command)

    @get("/entities", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def search_entities(
        self,
        entity_service: NamedDependency[EntityService],
        term: FromQuery[str],
        limit: FromQuery[int] = 20,
    ) -> Sequence[EntityRelevance]:
        """
        Entities matching what the curator is typing, most used first.

        The same read view as the relevance screen on purpose: the question a type-ahead answers is
        "which of these 3.808 names is the one I mean", and how many descriptions carry it is what
        separates two entities that differ by an abbreviation.
        """
        return entity_service.search_entities(term, limit)

    @get("/entities/relevance", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_entity_relevance(
        self,
        entity_service: NamedDependency[EntityService],
        entity_type: FromQuery[Literal["ORG", "PER", "LOC"] | None] = None,
        limit: FromQuery[int] = 30,
    ) -> EntityRelevanceResponse:
        results = entity_service.get_entity_relevance_count(entity_type, limit)
        return EntityRelevanceResponse(data=list(results))

    @get("/entities/similar", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_similar_entities(
        self,
        entity_service: NamedDependency[EntityService],
        target_name: FromQuery[str | None] = None,
        entity_type: FromQuery[Literal["ORG", "PER", "LOC"] | None] = None,
        threshold: FromQuery[float] = 0.5,
    ) -> EntitySimilarityResponse:

        if not target_name:
            results = entity_service.find_all_similar_entity_pairs(threshold)
            return EntitySimilarityResponse.from_payload(list(results))

        results = entity_service.find_similar(target_name, entity_type, threshold)
        return EntitySimilarityResponse.from_payload(list(results))

    @post("/entities/merge", opt={"access": Access.CURATE}, sync_to_thread=True)
    def merge_entities(
        self,
        entity_service: NamedDependency[EntityService],
        data: EntityMergeRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> EntityMergeResponse:
        """
        Unifies entities into the canonical one, optionally renaming it.

        The write is logged per absorbed entity in the ledger before anything changes, so the
        response carries the ``merge_ids`` the screen needs to offer the undo — without them the
        archivist would have to go find the row in the ledger to reverse the click they just made.
        """
        return entity_service.merge(
            MergeEntityCommand(
                canonical_id=data.canonical_id,
                ids_to_merge=data.ids_to_merge,
                new_name=data.new_name,
                changed_by=current_user.author,
                note=data.note,
            )
        )

    @post("/entities/merge/preview", opt={"access": Access.AUTHENTICATED}, status_code=200, sync_to_thread=True)
    def preview_entity_merge(
        self,
        entity_service: NamedDependency[EntityService],
        data: EntityMergePreviewRequest,
    ) -> EntityMergePreviewResponse:
        """
        Dry-run of an entity merge: how many links move, what is absorbed and what to review.

        Read-only, computed by the same planner the merge executes, so the preview cannot promise
        a different number from the write.
        """
        return entity_service.preview_merge(
            MergeEntityPreviewCommand(
                canonical_id=data.canonical_id, ids_to_merge=data.ids_to_merge, new_name=data.new_name
            )
        )

    @get("/entities/merge-log", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_entity_merge_log(
        self,
        entity_service: NamedDependency[EntityService],
        canonical_id: FromQuery[int | None] = None,
        changed_by: FromQuery[str | None] = None,
        include_undone: FromQuery[bool] = True,
        # ``q`` and not ``term``: the collection search already owns ``term`` for its own meaning,
        # and this one is a filter *inside* a ledger. The front reads the same name it sends.
        q: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> EntityMergeLogListResponse:
        """
        The audit trail of the entity merges: what was merged, by whom, and what was undone.

        ``q`` matches both sides of the entry — the absorbed and the canonical name — because the
        archivist asking "where did this spelling go?" does not know which side it was on.
        """
        return entity_service.list_merge_log(
            canonical_id=canonical_id,
            changed_by_name=changed_by,
            include_undone=include_undone,
            term=q,
            limit=limit,
            offset=offset,
        )

    @delete("/entities/merge-log/{merge_id:int}", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def undo_entity_merge(
        self,
        entity_service: NamedDependency[EntityService],
        merge_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> EntityMergeUndoResponse:
        """
        Undoes one merge from the ledger: the entity, its links and the canonical name come back.

        The second attempt is **409** and an unknown id is **404**; the ledger entry is never
        deleted, so the history of "this was merged, then undone" survives.
        """
        entry = entity_service.undo_merge(merge_id, undone_by=current_user.author)
        return EntityMergeUndoResponse(
            code=RouteMessageCode.ENTITY_MERGE_UNDONE,
            message=f"Mesclagem desfeita: a entidade '{entry.absorbed_name}' foi restaurada.",
            data=entry,
        )

    @post("/entities/orphans/purge", opt={"access": Access.CURATE}, sync_to_thread=True)
    def purge_orphan_entities(self, entity_service: NamedDependency[EntityService]) -> OrphanEntityPurgeResponse:
        deleted_count = entity_service.purge_orphan_entities()
        return OrphanEntityPurgeResponse(
            code=RouteMessageCode.ORPHAN_ENTITIES_PURGED,
            message="Limpeza de entidades órfãs concluída com sucesso.",
            entities_deleted=deleted_count,
        )

    @patch("/entities/{entity_id:int}/reclassify", opt={"access": Access.CURATE}, sync_to_thread=True)
    def reclassify_entity(
        self,
        entity_service: NamedDependency[EntityService],
        entity_id: FromPath[int],
        data: ReclassifyEntityRequest,
    ) -> EntityReclassifyResponse:
        entity_service.reclassify_entity(entity_id, data.new_type)
        return EntityReclassifyResponse(
            code=RouteMessageCode.ENTITY_RECLASSIFIED,
            message="Entidade reclassificada com sucesso e sinônimo de ancoragem gerado.",
            new_type=data.new_type,
        )

    @patch("/entities/{entity_id:int}", opt={"access": Access.CURATE}, sync_to_thread=True)
    def rename_entity(
        self,
        entity_service: NamedDependency[EntityService],
        entity_id: FromPath[int],
        data: EntityRenameRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> EntityRenameResponse:
        """
        Renames one name, with an undo of its own.

        Not a side effect of absorbing a twin — that is the merge — and not a label change either: the
        previous spelling stays anchored as a synonym unless the archivist said the edit was a typo,
        which is what ``keep_old_synonym`` decides. The ledger row is the undo the screen offers, the
        same one the merge writes; a name another entity already carries is a **409** that names the
        twin, because that twin is the merge case and not a collision to invent.
        """
        renamed, merge_id = entity_service.rename_entity(
            entity_id,
            data.new_name,
            keep_old_synonym=data.keep_old_synonym,
            changed_by=current_user.author,
            note=data.note,
        )
        return EntityRenameResponse(
            code=RouteMessageCode.ENTITY_RENAMED,
            message="Entidade renomeada com sucesso.",
            entity_id=renamed.entity_id,
            name=renamed.name,
            entity_type=renamed.entity_type,
            merge_id=merge_id,
            kept_old_spelling=data.keep_old_synonym,
        )

    @delete("/entities/{entity_id:int}", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def delete_entity(
        self, entity_service: NamedDependency[EntityService], entity_id: FromPath[int]
    ) -> EntityDeleteResponse:
        # The transaction (commit/rollback) is still guaranteed by the db_session injection
        entity_service.delete_entity(entity_id)

        return EntityDeleteResponse(
            code=RouteMessageCode.ENTITY_DELETED,
            message=f"Entidade {entity_id} excluída com sucesso da base de dados.",
        )

    # ==========================================
    # ROUTES: NER EXCLUSIONS (the subject axis owns the term)
    # ==========================================

    @get("/entities/ner-exclusions", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_ner_exclusions(self, entity_service: NamedDependency[EntityService]) -> list[NerExclusion]:
        """Lists the terms the curation keeps out of the NER extraction."""
        return list(entity_service.list_ner_exclusions())

    @post("/entities/ner-exclusions", opt={"access": Access.CURATE}, status_code=201, sync_to_thread=True)
    def create_ner_exclusions(
        self, entity_service: NamedDependency[EntityService], data: NerExclusionRequest
    ) -> NerExclusionBanResponse:
        """
        Bans terms from NER. **Nothing is deleted**: the entities already extracted from a banned
        spelling are removed by the purge below, a separate act with its own preview and ledger
        (#94). The ban is reversible through the ``DELETE`` on this same path.
        """
        created = entity_service.exclude_terms_from_ner(data.words, reason=data.reason)

        return NerExclusionBanResponse(
            code=RouteMessageCode.NER_EXCLUSIONS_ADDED,
            message="Termos marcados como assunto: o extrator não os tratará mais como entidade.",
            created=created,
        )

    @delete("/entities/ner-exclusions", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def remove_ner_exclusions(
        self, entity_service: NamedDependency[EntityService], data: NerExclusionRequest
    ) -> NerExclusionRemovalResponse:
        """
        Undoes the ban and re-opens the terms for the NER engine.

        It does not bring back what a purge deleted: that is the purge ledger's undo, which is where
        the entities and their links were recorded.
        """
        removed = entity_service.remove_ner_exclusions(data.words)

        return NerExclusionRemovalResponse(
            code=RouteMessageCode.NER_EXCLUSIONS_REMOVED,
            message=(
                "Exclusões removidas: o extrator voltará a considerar esses termos. "
                "As entidades já expurgadas voltam pelo desfazer da purga, não por aqui."
            ),
            removed=removed,
        )

    @post(
        "/entities/ner-exclusions/purge/preview",
        opt={"access": Access.AUTHENTICATED},
        status_code=200,
        sync_to_thread=True,
    )
    def preview_ner_purge(self, entity_service: NamedDependency[EntityService]) -> NerPurgePreview:
        """
        The dry run of the purge: the entities that would die, and the ledger that can bring them back.

        Every entity extracted from a banned spelling, with how many descriptions carry it, so the
        screen can show the loss before it happens. The list is the plan the purge itself consumes,
        so the preview and the write cannot disagree.
        """
        return entity_service.preview_ner_purge()

    @post("/entities/ner-exclusions/purge", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def purge_ner_entities(
        self, entity_service: NamedDependency[EntityService], current_user: NamedDependency[AuthenticatedUser]
    ) -> NerPurgeResponse:
        """
        Deletes every entity whose spelling is a banned term, after logging each one in the ledger.

        The write consumes the same plan the preview showed — no body, because the screen applies
        the list it approved. The response carries the ``purge_ids`` the screen needs to offer the
        undo; the veto itself stays in place.
        """
        result = entity_service.purge_ner_terms(current_user.author)
        return NerPurgeResponse(
            code=RouteMessageCode.NER_PURGE_DONE,
            message="Expurgo concluído: as entidades já extraídas foram removidas e podem ser restauradas.",
            entities_deleted=result.entities_deleted,
            purge_ids=result.purge_ids,
        )

    @get("/entities/ner-exclusions/purge-log", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_ner_purge_log(
        self,
        entity_service: NamedDependency[EntityService],
        include_undone: FromQuery[bool] = True,
        # ``q`` and not ``term``: the taxonomy search already owns ``term`` for its own meaning, and
        # this one is a filter *inside* a ledger. The front reads the same name it sends.
        q: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> NerPurgeLogListResponse:
        """The audit trail of the NER purges: what died, by whom, and what was restored."""
        return entity_service.list_ner_purge_log(include_undone=include_undone, term=q, limit=limit, offset=offset)

    @delete(
        "/entities/ner-exclusions/purge-log/{purge_id:int}",
        opt={"access": Access.CURATE},
        status_code=200,
        sync_to_thread=True,
    )
    def undo_ner_purge(
        self,
        entity_service: NamedDependency[EntityService],
        purge_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> NerPurgeUndoResponse:
        """
        Undoes one purge from the ledger: the entity, its links and its spellings come back.

        The second attempt is **409** and an unknown id is **404**; the ledger entry is never
        deleted, so the history of "this was purged, then restored" survives. The veto stays: the
        term is still excluded, and the next purge lists the restored entity again.
        """
        entry = entity_service.undo_ner_purge(purge_id, undone_by=current_user.author)
        return NerPurgeUndoResponse(
            code=RouteMessageCode.NER_PURGE_UNDONE,
            message=f"Expurgo desfeito: a entidade '{entry.purged_name}' foi restaurada.",
            data=entry,
        )

    # ==========================================
    # ROUTES: DOMAIN CLASH (Cross-Domain)
    # ==========================================

    @get("/conflicts/cross-domain", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_cross_domain_conflicts(
        self,
        entity_service: NamedDependency[EntityService],
        threshold: FromQuery[float] = 0.85,
        pair_kind: FromQuery[Literal["all", "exact_name", "near_duplicate"]] = "all",
        entity_type: FromQuery[EntityKind | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> CrossDomainConflictPage:
        """
        The collisions that exist **today**, annotated with what has already been decided.

        ``pair_kind`` is what makes the list usable rather than overwhelming: the trigram join returns
        thousands of pairs, most of them the same spelling on both axes (a structural question) and a
        minority the same word written differently (a spelling question). ``entity_type`` narrows the
        structural population to a category — the same selection the batch writes.

        Each pair carries the judge's verdict when there is one, so a pair the judge already doubted
        is not put in front of the archivist as if it were new.
        """
        return entity_service.page_cross_domain_conflicts(
            threshold=threshold, pair_kind=pair_kind, entity_type=entity_type, limit=limit, offset=offset
        )

    @get("/conflicts/judged", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_judged_conflicts(
        self,
        entity_service: NamedDependency[EntityService],
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> JudgedConflictPage:
        """
        What the judge decided, read from the review queue rather than from the live scan.

        This is the read that was missing. An auto-resolution deletes the losing row, so 84 of the
        88 decisions on the real collection cannot appear in a trigram join; the queue row survives
        because its payload is a snapshot without a foreign key. ``still_applicable`` counts the
        decisions that are still about something — both sides alive and nothing written.
        """
        return entity_service.list_judged_conflicts(limit=limit, offset=offset)

    @post("/conflicts/resolve/preview", opt={"access": Access.AUTHENTICATED}, status_code=200, sync_to_thread=True)
    def preview_conflict_resolution(
        self, entity_service: NamedDependency[EntityService], data: ConflictPreviewRequest
    ) -> ConflictResolutionPlan:
        """
        The dry run: what each verdict would transfer, delete and ban. **Nothing is written.**

        Computed by the same planner the apply executes, so the number the archivist approves is the
        number the write produces.
        """
        return entity_service.plan_conflict_resolution(data.tag_id, data.entity_id)

    @post("/conflicts/resolve", opt={"access": Access.CURATE}, sync_to_thread=True)
    def resolve_cross_domain_conflict(
        self,
        entity_service: NamedDependency[EntityService],
        data: ConflictResolutionRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> ConflictResolutionResponse:
        """
        Forces the victory of a Tag or an Entity, and records the write so it can be reversed.

        The response carries the ``resolution_id`` the screen needs to offer the undo — without it
        the archivist would have to go find the row in the ledger to reverse the click they just made.
        """
        result = entity_service.resolve_cross_domain_conflict(
            ResolveConflictCommand(
                winner=data.winner,
                tag_id=data.tag_id,
                entity_id=data.entity_id,
                decided_by=current_user.author,
                note=data.note,
            )
        )
        return ConflictResolutionResponse(
            code=RouteMessageCode.CONFLICT_RESOLVED,
            message=(
                f"Conflito resolvido a favor de {data.winner}: "
                f"{result.documents_transferred} vínculo(s) transferido(s). A resolução pode ser desfeita."
            ),
            data=result,
        )

    @post("/conflicts/resolve/batch", opt={"access": Access.CURATE}, sync_to_thread=True)
    def resolve_cross_domain_conflict_batch(
        self,
        entity_service: NamedDependency[EntityService],
        data: ConflictBatchRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> ConflictBatchResponse:
        """
        Forces one verdict over a whole **selection**, one ledger row — and one undo — per pair.

        ``pair_kind`` picks the structural population the batch is meaningful for and ``entity_type``
        narrows it to a category: "a street is an entity" is a decision about a set, and a screen that
        asks one pair at a time cannot express it. The report keeps ``skipped`` apart from ``failed``
        — a pair an earlier one of the same batch already finished is not an error — and the
        remaining count is the read the screen already uses, taken again.
        """
        result = entity_service.resolve_conflict_batch(
            ResolveConflictBatchCommand(
                winner=data.winner,
                pair_kind=data.pair_kind,
                entity_type=data.entity_type,
                threshold=data.threshold,
                limit=data.limit,
                decided_by=current_user.author,
                note=data.note,
            )
        )

        message = (
            f"{len(result.applied)} colisão(ões) resolvida(s) a favor de {data.winner} em lote; "
            f"{result.remaining.total} continua(m) na seleção."
        )
        if result.skipped:
            message += f" {len(result.skipped)} já não tinha(m) o que resolver."
        if result.failed:
            message += f" {len(result.failed)} falhou(aram)."

        return ConflictBatchResponse(code=RouteMessageCode.CONFLICT_BATCH_RESOLVED, message=message, data=result)

    @get("/conflicts/resolutions", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_conflict_resolutions(
        self,
        entity_service: NamedDependency[EntityService],
        include_undone: FromQuery[bool] = True,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> ConflictResolutionLogListResponse:
        """The audit trail of the resolutions: what was written, by whom, and what was reversed."""
        items, total = entity_service.list_conflict_resolutions(
            include_undone=include_undone, limit=limit, offset=offset
        )
        return ConflictResolutionLogListResponse(total=total, limit=limit, offset=offset, items=items)

    @delete(
        "/conflicts/resolutions/{resolution_id:int}",
        opt={"access": Access.CURATE},
        status_code=200,
        sync_to_thread=True,
    )
    def undo_conflict_resolution(
        self,
        entity_service: NamedDependency[EntityService],
        resolution_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> dict:
        """
        Reverses one resolution: the losing row, its links and the ban it planted.

        The second attempt is **409** and an unknown id is **404**; the ledger entry is never
        deleted, so "this was resolved, then reversed" survives the reversal.
        """
        entry = entity_service.undo_conflict_resolution(resolution_id, undone_by=current_user.author)
        return {
            "message": (
                f"Resolução {resolution_id} desfeita: {entry.documents_transferred} vínculo(s) "
                f"voltaram e {entry.ban_term or 'nenhum termo'} saiu do bloqueio."
            ),
            "data": entry.model_dump(),
        }

# api/controllers/taxonomy_controller.py
from collections.abc import Sequence
from typing import Literal

import anyio
import anyio.to_process
from litestar import Controller, delete, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from memoria_curitibana.api.dependencies import provide_entity_service, provide_tag_service
from memoria_curitibana.api.schemas.taxonomy import (
    ConflictResolutionRequest,
    ConflictResolutionResponse,
    CrossDomainConflictListResponse,
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
    StopwordRemovalRequest,
    StopwordsRequest,
    SubjectExclusionRequest,
    SuggestMacroRequest,
    TagCurationRequest,
)
from memoria_curitibana.domains.archive.models.enums import StopwordsScope
from memoria_curitibana.domains.archive.schemas import (
    ArchiveMacroCategoryEntityDTO,
    BatchMergeResponse,
    CreateMacroCategoryCommand,
    MergeBatchCommand,
    MergeEntityCommand,
    MergeLogListResponse,
    MergePreviewCommand,
    MergePreviewResponse,
    MergeSuggestionRunResponse,
    MergeTagsCommand,
    ResolveConflictCommand,
    StopwordDTO,
    StopwordPurgePreview,
    TagCurationCommand,
    TagCurationResult,
    TagMergeDecisionCommand,
    TagMergeProposalListResponse,
    TagSearchResult,
    UpdateMacroCategoryCommand,
)
from memoria_curitibana.domains.archive.schemas.entity_schema import (
    EntityDeleteResponse,
    EntityMergeResponse,
    EntityReclassifyResponse,
    EntityRelevance,
    EntityRelevanceResponse,
    EntitySimilarityResponse,
    EntityStopwordPurgeResponse,
    NerExclusion,
    NerExclusionBanResponse,
    NerExclusionRemovalResponse,
    OrphanEntityPurgeResponse,
)
from memoria_curitibana.domains.archive.schemas.tag_schema import (
    MacroCategoriesSuggestionResponse,
    MergeResponse,
    StopwordBanResponse,
    StopwordPurgeResponse,
    StopwordRemovalResponse,
    SubjectExclusionBanResponse,
    SubjectExclusionRemovalResponse,
    TagMergeProposalDecisionResponse,
    TagMergeUndoResponse,
    TagPairSimilarity,
    TagRelevanceResponse,
    TagSimilarity,
)
from memoria_curitibana.domains.archive.services.entity_service import EntityService
from memoria_curitibana.domains.archive.services.tag_service import TagService


class TaxonomyController(Controller):
    path = "/api/v1/taxonomy"
    tags = ["Taxonomy"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "tag_service": Provide(provide_tag_service, sync_to_thread=False),
        "entity_service": Provide(provide_entity_service, sync_to_thread=False),
    }

    @get("/tags", sync_to_thread=True)
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

    @patch("/tags/{tag_id:int}", sync_to_thread=True)
    def curate_tag(
        self,
        tag_service: NamedDependency[TagService],
        tag_id: FromPath[int],
        data: TagCurationRequest,
    ) -> TagCurationResult:
        """
        Moves one tag into a subject drawer, or declares that it is not a subject at all.

        A global decision about the vocabulary, not a local edit: it changes the badge of every
        description that carries the tag, and the response says as much by being the tag itself.
        """
        return tag_service.curate_tag_macro_category(tag_id, TagCurationCommand(**data.model_dump()))

    @get("/tags/relevance/{method:str}", sync_to_thread=True)
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

    @get("/tags/similar", sync_to_thread=True)
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

    @post("/tags/merge", sync_to_thread=True)
    def merge_tags(self, tag_service: NamedDependency[TagService], data: MergeRequest) -> MergeResponse:
        response = tag_service.merge(
            MergeTagsCommand(
                canonical_id=data.canonical_id,
                ids_to_merge=data.ids_to_merge,
                changed_by=data.changed_by,
            )
        )

        return response

    @post("/tags/merge/preview", status_code=200, sync_to_thread=True)
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

    @post("/tags/merge-proposals/suggest", status_code=200, sync_to_thread=True)
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

    @get("/tags/merge-proposals", sync_to_thread=True)
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

    @patch("/tags/merge-proposals/{proposal_id:int}", sync_to_thread=True)
    def decide_tag_merge_proposal(
        self,
        tag_service: NamedDependency[TagService],
        proposal_id: FromPath[int],
        data: MergeProposalDecisionRequest,
    ) -> TagMergeProposalDecisionResponse:
        """Approves or rejects a proposed cluster. Approval records intent, it does not merge."""
        proposal = tag_service.decide_merge_proposal(
            proposal_id,
            TagMergeDecisionCommand(status=data.status, decided_by=data.decided_by, note=data.note),
        )
        return TagMergeProposalDecisionResponse(
            message="Decisão registrada. A mesclagem só será aplicada quando o lote for executado.",
            data=proposal,
        )

    @post("/tags/merge/batch", status_code=200, sync_to_thread=True)
    def apply_tag_merge_batch(
        self,
        tag_service: NamedDependency[TagService],
        data: MergeBatchRequest,
    ) -> BatchMergeResponse:
        """
        Applies a batch of proposals, one savepoint per cluster, and reports each outcome.

        The write is logged in the ledger, so every cluster applied here can be undone
        individually through ``DELETE /tags/merge-log/{merge_id}``.
        """
        return tag_service.merge_batch(
            MergeBatchCommand(proposal_ids=data.proposal_ids, changed_by=data.changed_by, note=data.note)
        )

    @get("/tags/merge-log", sync_to_thread=True)
    def list_tag_merge_log(
        self,
        tag_service: NamedDependency[TagService],
        canonical_id: FromQuery[int | None] = None,
        changed_by: FromQuery[str | None] = None,
        include_undone: FromQuery[bool] = True,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> MergeLogListResponse:
        """The audit trail of the merges: what was merged, by whom, and what was undone."""
        return tag_service.list_merge_log(
            canonical_id=canonical_id,
            changed_by=changed_by,
            include_undone=include_undone,
            limit=limit,
            offset=offset,
        )

    @delete("/tags/merge-log/{merge_id:int}", status_code=200, sync_to_thread=True)
    def undo_tag_merge(
        self,
        tag_service: NamedDependency[TagService],
        merge_id: FromPath[int],
        undone_by: FromQuery[str | None] = None,
    ) -> TagMergeUndoResponse:
        """
        Undoes one merge from the ledger: the tag, its links, its classification and its
        spellings come back exactly as they were.
        """
        entry = tag_service.undo_merge(merge_id, undone_by=undone_by)
        return TagMergeUndoResponse(
            message=f"Mesclagem desfeita: a tag '{entry.absorbed_name}' foi restaurada.",
            data=entry,
        )

    @get("/tags/stopwords", sync_to_thread=True)
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

    @post("/tags/stopwords", status_code=201, sync_to_thread=True)
    def create_stopwords(
        self,
        tag_service: NamedDependency[TagService],
        data: StopwordCreateRequest,
    ) -> StopwordBanResponse:
        """Bans terms. Banning does not delete anything: the purge is a separate, explicit step."""
        created = tag_service.save_new_stopwords(data.words, data.scope)
        return StopwordBanResponse(
            message=f"{created} stopword(s) registrada(s) no eixo {data.scope}.",
            created=created,
        )

    @delete("/tags/stopwords", status_code=200, sync_to_thread=True)
    def remove_stopwords(
        self,
        tag_service: NamedDependency[TagService],
        data: StopwordRemovalRequest,
    ) -> StopwordRemovalResponse:
        """Un-bans terms — the only way back from a purge decision, since the purge has no undo."""
        removed = tag_service.remove_stopwords(data.words, data.scope)
        return StopwordRemovalResponse(message=f"{removed} stopword(s) removida(s).", removed=removed)

    @post("/tags/stopwords/purge/preview", status_code=200, sync_to_thread=True)
    def preview_stopword_purge(self, tag_service: NamedDependency[TagService]) -> StopwordPurgePreview:
        """
        The dry run of the only destructive operation in the taxonomy without an undo.

        It lists the tags the purge would delete, with how many descriptions carry each and which
        drawer dies with it, so the screen can show the loss before it happens.
        """
        return tag_service.preview_stopword_purge()

    @post("/tags/stopwords/purge", status_code=200, sync_to_thread=True)
    def purge_stopwords(
        self, tag_service: NamedDependency[TagService], data: StopwordsRequest
    ) -> StopwordPurgeResponse:
        """
        Deletes every tag whose name is a banned term. **There is no undo for this one.**

        ``words`` is optional and, when sent, is registered before the purge, so a client may ban and
        purge in one call. The screen sends an **empty body**: it purges with the list it already
        showed in the preview, so the numbers the archivist approved are the numbers that die.
        """
        if data.words:
            tag_service.save_new_stopwords(data.words)

        deleted_count = tag_service.purge_stopwords()
        return StopwordPurgeResponse(message="Limpeza concluída com sucesso.", tags_deleted=deleted_count)

    @post("/tags/suggest-macro")
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
        from memoria_curitibana.domains.archive.workers.worker_suggest_macro_category import (
            MIN_TEXTS_TO_CLUSTER,
            run_suggestion_engine,
        )

        if not texts_to_analyze or len(texts_to_analyze) < MIN_TEXTS_TO_CLUSTER:
            return MacroCategoriesSuggestionResponse(
                total_suggestions=0, categories=[], message="⚠️ Textos insuficientes para formar clusters semânticos."
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

    @get("/tags/subject-exclusions", sync_to_thread=True)
    def list_subject_exclusions(self, tag_service: NamedDependency[TagService]) -> list[str]:
        """Lists the terms the curation decided are not a subject."""
        return tag_service.list_subject_exclusions()

    @post("/tags/subject-exclusions", status_code=201, sync_to_thread=True)
    def create_subject_exclusions(
        self, tag_service: NamedDependency[TagService], data: SubjectExclusionRequest
    ) -> SubjectExclusionBanResponse:
        """
        Records that a term is not a subject, so the classifier stops guessing at it.

        Nothing is deleted: the term stays a tag of the collection and stays reachable by
        search. Only the subject classification is silenced, which is what turns "the model
        answers confidently and wrongly" into "the curator decided".
        """
        created = tag_service.exclude_terms_from_subjects(data.words, reason=data.reason)
        return SubjectExclusionBanResponse(
            message="Termos marcados como não-assunto: o classificador de assuntos vai ignorá-los.",
            created=created,
        )

    @delete("/tags/subject-exclusions", status_code=200, sync_to_thread=True)
    def remove_subject_exclusions(
        self, tag_service: NamedDependency[TagService], data: SubjectExclusionRequest
    ) -> SubjectExclusionRemovalResponse:
        """Undoes the decision and puts the terms back in the classification queue."""
        removed = tag_service.remove_subject_exclusions(data.words)
        return SubjectExclusionRemovalResponse(
            message="Exclusões removidas: o classificador voltará a considerar esses termos.",
            removed=removed,
        )

    @get("/macro-categories", sync_to_thread=True)
    def list_macro_categories(
        self,
        tag_service: NamedDependency[TagService],
        only_active: FromQuery[bool] = False,
    ) -> list[ArchiveMacroCategoryEntityDTO]:
        """Lists the official macro categories (the subject axis of the collection)."""
        return tag_service.list_macro_categories(only_active=only_active)

    @post("/macro-categories", sync_to_thread=True)
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

    @patch("/macro-categories/{category_id:int}", sync_to_thread=True)
    def update_macro_category(
        self,
        tag_service: NamedDependency[TagService],
        category_id: FromPath[int],
        data: MacroCategoryUpdateRequest,
    ) -> ArchiveMacroCategoryEntityDTO:
        """Renames, re-describes, rewrites the classifier label or (de)activates a macro category."""
        command = UpdateMacroCategoryCommand(**data.model_dump(exclude_unset=True))
        return tag_service.update_macro_category(category_id, command)

    @get("/entities", sync_to_thread=True)
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

    @get("/entities/relevance", sync_to_thread=True)
    def get_entity_relevance(
        self,
        entity_service: NamedDependency[EntityService],
        entity_type: FromQuery[Literal["ORG", "PER", "LOC"] | None] = None,
        limit: FromQuery[int] = 30,
    ) -> EntityRelevanceResponse:
        results = entity_service.get_entity_relevance_count(entity_type, limit)
        return EntityRelevanceResponse(data=list(results))

    @get("/entities/similar", sync_to_thread=True)
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

    @post("/entities/merge", sync_to_thread=True)
    def merge_entities(self, entity_service: NamedDependency[EntityService], data: MergeRequest) -> EntityMergeResponse:
        """Merges entities into the canonical one, answering with the same shape the tag merge uses."""
        res = entity_service.merge(
            MergeEntityCommand(canonical_id=data.canonical_id, ids_to_merge=data.ids_to_merge, new_name=data.new_name)
        )
        return EntityMergeResponse(documents_updated=res.documents_updated, entities_deleted=res.entities_deleted)

    @post("/entities/orphans/purge", sync_to_thread=True)
    def purge_orphan_entities(self, entity_service: NamedDependency[EntityService]) -> OrphanEntityPurgeResponse:
        deleted_count = entity_service.purge_orphan_entities()
        return OrphanEntityPurgeResponse(
            message="Limpeza de entidades órfãs concluída com sucesso.",
            entities_deleted=deleted_count,
        )

    @post("/entities/stopwords/purge_stopwords", sync_to_thread=True)
    def purge_entity_stopwords(
        self, entity_service: NamedDependency[EntityService], data: StopwordsRequest
    ) -> EntityStopwordPurgeResponse:
        deleted_count = entity_service.purge_entity_stopwords(data.words)

        return EntityStopwordPurgeResponse(
            message="Falsos positivos adicionados à lista negra e expurgados com sucesso.",
            entities_deleted=deleted_count,
        )

    @patch("/entities/{entity_id:int}/reclassify", sync_to_thread=True)
    def reclassify_entity(
        self,
        entity_service: NamedDependency[EntityService],
        entity_id: FromPath[int],
        data: ReclassifyEntityRequest,
    ) -> EntityReclassifyResponse:
        entity_service.reclassify_entity(entity_id, data.new_type)
        return EntityReclassifyResponse(
            message="Entidade reclassificada com sucesso e sinônimo de ancoragem gerado.",
            new_type=data.new_type,
        )

    @delete("/entities/{entity_id:int}", status_code=200, sync_to_thread=True)
    def delete_entity(
        self, entity_service: NamedDependency[EntityService], entity_id: FromPath[int]
    ) -> EntityDeleteResponse:
        # The transaction (commit/rollback) is still guaranteed by the db_session injection
        entity_service.delete_entity(entity_id)

        return EntityDeleteResponse(message=f"Entidade {entity_id} excluída com sucesso da base de dados.")

    # ==========================================
    # ROUTES: NER EXCLUSIONS (the subject axis owns the term)
    # ==========================================

    @get("/entities/ner-exclusions", sync_to_thread=True)
    def list_ner_exclusions(self, entity_service: NamedDependency[EntityService]) -> list[NerExclusion]:
        """Lists the terms the curation keeps out of the NER extraction."""
        return list(entity_service.list_ner_exclusions())

    @post("/entities/ner-exclusions", status_code=201, sync_to_thread=True)
    def create_ner_exclusions(
        self, entity_service: NamedDependency[EntityService], data: NerExclusionRequest
    ) -> NerExclusionBanResponse:
        """Bans terms from NER and purges the entities already extracted from them."""
        entities_deleted = entity_service.exclude_terms_from_ner(data.words, reason=data.reason)

        return NerExclusionBanResponse(
            message="Termos marcados como assunto: o extrator não os tratará mais como entidade.",
            entities_deleted=entities_deleted,
        )

    @delete("/entities/ner-exclusions", status_code=200, sync_to_thread=True)
    def remove_ner_exclusions(
        self, entity_service: NamedDependency[EntityService], data: NerExclusionRequest
    ) -> NerExclusionRemovalResponse:
        """Undoes the ban and re-opens the terms for the NER engine."""
        removed = entity_service.remove_ner_exclusions(data.words)

        return NerExclusionRemovalResponse(
            message="Exclusões removidas: o extrator voltará a considerar esses termos.", removed=removed
        )

    # ==========================================
    # ROUTES: DOMAIN CLASH (Cross-Domain)
    # ==========================================

    @get("/conflicts/cross-domain", sync_to_thread=True)
    def get_cross_domain_conflicts(
        self,
        entity_service: NamedDependency[EntityService],
        threshold: FromQuery[float] = 0.85,
    ) -> CrossDomainConflictListResponse:
        """Returns a list of conflicts where Tags and Entities share the same naming."""
        results = entity_service.find_cross_domain_conflicts(threshold=threshold)
        return CrossDomainConflictListResponse(data=list(results))

    @post("/conflicts/resolve", sync_to_thread=True)
    def resolve_cross_domain_conflict(
        self, entity_service: NamedDependency[EntityService], data: ConflictResolutionRequest
    ) -> ConflictResolutionResponse:
        """Resolves the conflict by forcing the victory of a Tag or an Entity."""
        result = entity_service.resolve_cross_domain_conflict(
            ResolveConflictCommand(winner=data.winner, tag_id=data.tag_id, entity_id=data.entity_id)
        )
        return ConflictResolutionResponse(
            message=f"Conflito resolvido! A vitória foi concedida para {data.winner}.", data=result
        )

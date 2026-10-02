# api/controllers/taxonomy_controller.py
from typing import Literal

import anyio
import anyio.to_process
from litestar import Controller, delete, get, patch, post
from litestar.di import Provide

from api.dependencies import provide_entity_service, provide_tag_service
from api.schemas.taxonomy import (
    ConflictResolutionRequest,
    ConflictResolutionResponse,
    CrossDomainConflictListResponse,
    MergeRequest,
    ReclassifyEntityRequest,
    StopwordsRequest,
    SuggestMacroRequest,
)
from domains.archive.schemas import MergeEntityCommand, MergeTagsCommand, ResolveConflictCommand
from domains.archive.schemas.entity_schema import EntityRelevanceResponse, EntitySimilarityResponse
from domains.archive.schemas.tag_schema import (
    MacroCategoriesSuggestionResponse,
    MergeResponse,
    TagPairSimilarity,
    TagRelevanceResponse,
    TagSimilarity,
)
from domains.archive.services.entity_service import EntityService
from domains.archive.services.tag_service import TagService
from domains.archive.workers.worker_suggest_macro_category import run_suggestion_engine


class TaxonomyController(Controller):
    path = "/api/v1/taxonomy"
    tags = ["Taxonomy"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "tag_service": Provide(provide_tag_service),
        "entity_service": Provide(provide_entity_service),
    }

    @get("/tags/relevance/{method:str}", sync_to_thread=True)
    def get_tag_relevance(
        self, tag_service: TagService, method: Literal["tfidf", "count"] = "tfidf", limit: int = 30
    ) -> TagRelevanceResponse:

        if method == "tfidf":
            results = tag_service.get_tag_relevance_tfidf(limit)
        else:
            results = tag_service.get_tag_relevance_count(limit)

        return TagRelevanceResponse.from_payload(list(results))

    @get("/tags/similar", sync_to_thread=True)
    def get_similar_tags(
        self, tag_service: TagService, target: str | None = None, threshold: float = 0.4
    ) -> list[TagSimilarity] | list[TagPairSimilarity]:

        if not target:
            results = tag_service.find_all_similar_tag_pairs(threshold)
            return list(results)

        results = tag_service.find_similar_tags(target, threshold)
        return list(results)

    @post("/tags/merge", sync_to_thread=False)
    def merge_tags(self, tag_service: TagService, data: MergeRequest) -> MergeResponse:
        response = tag_service.merge(MergeTagsCommand(canonical_id=data.canonical_id, ids_to_merge=data.ids_to_merge))

        return response

    @post("/tags/stopwords/purge", sync_to_thread=False)
    def purge_stopwords(self, tag_service: TagService, data: StopwordsRequest) -> dict:

        if data.words:
            tag_service.save_new_stopwords(data.words)

        deleted_count = tag_service.purge_stopwords()
        return {"message": "Limpeza concluída com sucesso.", "tags_deleted": deleted_count}

    @post("/tags/suggest-macro")
    async def suggest_macro_categories(
        self, tag_service: TagService, data: SuggestMacroRequest
    ) -> MacroCategoriesSuggestionResponse:

        texts_to_analyze = tag_service.get_text_to_suggest_macro_category(
            source_type=data.source_type, columns_to_extract=data.columns_to_extract
        )

        if not texts_to_analyze or len(texts_to_analyze) < 10:
            return MacroCategoriesSuggestionResponse(
                total_suggestions=0, categories=[], message="⚠️ Textos insuficientes para formar clusters semânticos."
            )

        # anyio.to_process.run_sync receives the function and then its positional arguments.
        results = await anyio.to_process.run_sync(
            run_suggestion_engine,
            texts_to_analyze,  # We pass source_type positionally
        )

        return results

    @get("/entities/relevance", sync_to_thread=True)
    def get_entity_relevance(
        self, entity_service: EntityService, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> EntityRelevanceResponse:
        results = entity_service.get_entity_relevance_count(entity_type, limit)
        return EntityRelevanceResponse(data=list(results))

    @get("/entities/similar", sync_to_thread=True)
    def get_similar_entities(
        self,
        entity_service: EntityService,
        target_name: str | None = None,
        entity_type: Literal["ORG", "PER", "LOC"] | None = None,
        threshold: float = 0.5,
    ) -> EntitySimilarityResponse:

        if not target_name:
            results = entity_service.find_all_similar_entity_pairs(threshold)
            return EntitySimilarityResponse.from_payload(list(results))

        results = entity_service.find_similar(target_name, entity_type, threshold)
        return EntitySimilarityResponse.from_payload(list(results))

    @post("/entities/merge", sync_to_thread=False)
    def merge_entities(self, entity_service: EntityService, data: MergeRequest) -> dict[str, int]:
        res = entity_service.merge(
            MergeEntityCommand(canonical_id=data.canonical_id, ids_to_merge=data.ids_to_merge, new_name=data.new_name)
        )

        # TODO Create an entity MergeResponse or recycle the tag one
        return {"documents_updated": res.documents_updated, "entities_deleted": res.entities_deleted}

    @post("/entities/orphans/purge", sync_to_thread=False)
    def purge_orphan_entities(self, entity_service: EntityService) -> dict:
        deleted_count = entity_service.purge_orphan_entities()
        return {"message": "Limpeza de entidades órfãs concluída com sucesso.", "entities_deleted": deleted_count}

    @post("/entities/stopwords/purge_stopwords", sync_to_thread=False)
    def purge_entity_stopwords(self, entity_service: EntityService, data: StopwordsRequest) -> dict:
        deleted_count = entity_service.purge_entity_stopwords(data.words)

        return {
            "message": "Falsos positivos adicionados à lista negra e expurgados com sucesso.",
            "entities_deleted": deleted_count,
        }

    @patch("/entities/{entity_id:int}/reclassify", sync_to_thread=False)
    def reclassify_entity(self, entity_service: EntityService, entity_id: int, data: ReclassifyEntityRequest) -> dict:
        entity_service.reclassify_entity(entity_id, data.new_type)
        return {
            "message": "Entidade reclassificada com sucesso e sinônimo de ancoragem gerado.",
            "new_type": data.new_type,
        }

    @delete("/entities/{entity_id:int}", status_code=200, sync_to_thread=False)
    def delete_entity(self, entity_service: EntityService, entity_id: int) -> dict:
        # The transaction (commit/rollback) is still guaranteed by the db_session injection
        entity_service.delete_entity(entity_id)

        return {"message": f"Entidade {entity_id} excluída com sucesso da base de dados."}

    # ==========================================
    # ROUTES: DOMAIN CLASH (Cross-Domain)
    # ==========================================

    @get("/conflicts/cross-domain", sync_to_thread=True)
    def get_cross_domain_conflicts(
        self, entity_service: EntityService, threshold: float = 0.85
    ) -> CrossDomainConflictListResponse:
        """Returns a list of conflicts where Tags and Entities share the same naming."""
        results = entity_service.find_cross_domain_conflicts(threshold=threshold)
        return CrossDomainConflictListResponse(data=list(results))

    @post("/conflicts/resolve", sync_to_thread=False)
    def resolve_cross_domain_conflict(
        self, entity_service: EntityService, data: ConflictResolutionRequest
    ) -> ConflictResolutionResponse:
        """Resolves the conflict by forcing the victory of a Tag or an Entity."""
        result = entity_service.resolve_cross_domain_conflict(
            ResolveConflictCommand(winner=data.winner, tag_id=data.tag_id, entity_id=data.entity_id)
        )
        return ConflictResolutionResponse(
            message=f"Conflito resolvido! A vitória foi concedida para {data.winner}.", data=result
        )

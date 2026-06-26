# api/controllers/taxonomy_controller.py
from typing import Literal

import anyio
import anyio.to_process
from litestar import Controller, delete, get, patch, post
from litestar.di import Provide

from api.dependencies import provide_entity_service, provide_tag_service
from api.schemas.taxonomy import MergeRequest, ReclassifyEntityRequest, StopwordsRequest, SuggestMacroRequest
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

    @get("/tags/relevance/{method:str}")
    def get_tag_relevance(
        self, tag_service: TagService, method: Literal["tfidf", "count"] = "tfidf", limit: int = 30
    ) -> TagRelevanceResponse:

        if method == "tfidf":
            resultados = tag_service.get_tag_relevance_tfidf(limit)
        else:
            resultados = tag_service.get_tag_relevance_count(limit)

        return TagRelevanceResponse.from_payload(list(resultados))

    @get("/tags/similar")
    def get_similar_tags(
        self, tag_service: TagService, target: str | None = None, threshold: float = 0.4
    ) -> list[TagSimilarity] | list[TagPairSimilarity]:

        if not target:
            results = tag_service.find_all_similar_tag_pairs(threshold)
            return list(results)

        results = tag_service.find_similar_tags(target, threshold)
        return list(results)

    @post("/tags/merge")
    def merge_tags(self, tag_service: TagService, data: MergeRequest) -> MergeResponse:
        response = tag_service.merge(data.canonical_id, data.ids_to_merge)

        return response

    @post("/tags/stopwords/purge")
    def purge_stopwords(self, tag_service: TagService, data: StopwordsRequest) -> dict:

        if data.words:
            tag_service.save_new_stopwords(data.words)

        qtd_apagadas = tag_service.purge_stopwords()
        return {"message": "Limpeza concluída com sucesso.", "tags_deleted": qtd_apagadas}

    @post("/tags/suggest-macro")
    async def suggest_macro_categories(
        self, tag_service: TagService, data: SuggestMacroRequest
    ) -> MacroCategoriesSuggestionResponse:

        texts_to_analize = tag_service.get_text_to_suggest_macro_category(
            source_type=data.source_type, columns_to_extract=data.columns_to_extract
        )

        if not texts_to_analize or len(texts_to_analize) < 10:
            return MacroCategoriesSuggestionResponse(
                total_suggestions=0, categories=[], message="⚠️ Textos insuficientes para formar clusters semânticos."
            )

        # anyio.to_process.run_sync recebe a função e depois os seus argumentos posicionais.
        results = await anyio.to_process.run_sync(
            run_suggestion_engine,
            texts_to_analize,  # Passamos o source_type posicionalmente
        )

        return results

    @get("/entities/relevance")
    def get_entity_relevance(
        self, entity_service: EntityService, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> EntityRelevanceResponse:
        resultados = entity_service.get_entity_relevance_count(entity_type, limit)
        return EntityRelevanceResponse(data=list(resultados))

    @get("/entities/similar")
    def get_similar_entities(
        self,
        entity_service: EntityService,
        target_name: str | None = None,
        entity_type: Literal["ORG", "PER", "LOC"] | None = None,
        threshold: float = 0.5,
    ) -> EntitySimilarityResponse:

        if not target_name:
            resultados = entity_service.find_all_similar_entity_pairs(threshold)
            return EntitySimilarityResponse.from_payload(list(resultados))

        resultados = entity_service.find_similar(target_name, entity_type, threshold)
        return EntitySimilarityResponse.from_payload(list(resultados))

    @post("/entities/merge")
    def merge_entities(self, entity_service: EntityService, data: MergeRequest) -> dict[str, int]:
        res = entity_service.merge(data.canonical_id, data.ids_to_merge)

        # TODO Fazer um mergeResponse da entity ou reciclar o da tag
        return {"documents_updated": res.documents_updated, "entities_deleted": res.entities_deleted}

    @post("/entities/orphans/purge")
    def purge_orphan_entities(self, entity_service: EntityService) -> dict:
        qtd_apagadas = entity_service.purge_orphan_entities()
        return {"message": "Limpeza de entidades órfãs concluída com sucesso.", "entities_deleted": qtd_apagadas}

    @post("/entities/stopwords/purge_stopwords")
    def purge_entity_stopwords(self, entity_service: EntityService, data: StopwordsRequest) -> dict:
        qtd_apagadas = entity_service.purge_entity_stopwords(data.words)

        return {
            "message": "Falsos positivos adicionados à lista negra e expurgados com sucesso.",
            "entities_deleted": qtd_apagadas,
        }

    @patch("/entities/{entity_id:int}/reclassify")
    def reclassify_entity(self, entity_service: EntityService, entity_id: int, data: ReclassifyEntityRequest) -> dict:
        entity_service.reclassify_entity(entity_id, data.new_type)
        return {
            "message": "Entidade reclassificada com sucesso e sinônimo de ancoragem gerado.",
            "new_type": data.new_type,
        }

    @delete("/entities/{entity_id:int}", status_code=200)
    def delete_entity(self, entity_service: EntityService, entity_id: int) -> dict:
        # A transação (commit/rollback) continua garantida pela injeção db_session
        entity_service.delete_entity(entity_id)

        return {"message": f"Entidade {entity_id} excluída com sucesso da base de dados."}

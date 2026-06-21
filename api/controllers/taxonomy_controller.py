# api/controllers/taxonomy_controller.py
from typing import Literal

import anyio
import anyio.to_process
from litestar import Controller, get, post
from litestar.di import Provide

from api.dependencies import provide_tag_service
from api.schemas.taxonomy import MergeRequest, StopwordsRequest, SuggestMacroRequest
from domains.archive.schemas.tag_schema import (
    MacroCategoriesSuggestionResponse,
    MergeResponse,
    TagRelevanceResponse,
    TagSimilarity,
)
from domains.archive.services.tag_service import TagService
from domains.archive.workers.worker_suggest_macro_category import run_suggestion_engine


class TaxonomyController(Controller):
    path = "/api/v1/taxonomy"
    tags = ["Taxonomy"]  # noqa: RUF012

    dependencies = {"tag_service": Provide(provide_tag_service)}  # noqa: RUF012

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
    def get_similar_tags(self, tag_service: TagService, target: str, threshold: float = 0.4) -> list[TagSimilarity]:

        results = tag_service.find_similar_tags(target, threshold)
        return list(results)

    @post("/tags/merge")
    def merge_tags(self, tag_service: TagService, data: MergeRequest) -> MergeResponse:
        response = tag_service.merge_tags(data.canonical_id, data.ids_to_merge)

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

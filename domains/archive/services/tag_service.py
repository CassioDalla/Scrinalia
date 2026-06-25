import re
from collections.abc import Sequence
from typing import Literal

from core.logger import logger
from domains.archive.exceptions import InvalidMergeError, InvalidParam
from domains.archive.repository import DocumentRepository
from domains.archive.repository.tag_repo import TagRepository
from domains.archive.schemas import (
    ArchiveTagDTO,
    MergeResponse,
    TagPairSimilarity,
    TagRelevanceCount,
    TagRelevanceIdf,
    TagSimilarity,
)


class TagService:
    """
    Serviço de domínio responsável por auditar, higienizar e unificar
    a taxonomia e as tags na camada Archive.
    """

    def __init__(self, repo: TagRepository, document_repo: DocumentRepository):
        self.repo = repo
        self.document_repo = document_repo
        self._stopwords_regex = None

    def _get_stopwords_regex(self) -> re.Pattern:
        """
        Busca as stopwords no banco apenas uma vez e compila um super-regex.
        """
        if self._stopwords_regex is None:
            # Puxa do banco
            stopwords = self.repo.get_stopwords()

            if stopwords:
                # Escapa os caracteres especiais das stopwords (caso haja algum '+', '.', etc)
                # e junta tudo com o pipe '|' (Operador OR)
                words = "|".join(re.escape(w) for w in stopwords)
                pattern = rf"\b({words})\b"

                # Compila o regex com a flag de ignorar maiúsculas/minúsculas
                self._stopwords_regex = re.compile(pattern, flags=re.IGNORECASE)
            else:
                # Se o banco estiver vazio, cria um regex que nunca dá match
                self._stopwords_regex = re.compile(r"a^")

        return self._stopwords_regex

    def extract_and_clean_tags(self, indexing_points: str | None) -> list[ArchiveTagDTO]:
        """
        Lê os pontos de indexação brutos (separados por vírgula), aplica
        o dicionário de stopwords do banco de dados e retorna os contratos validados.
        """
        if not indexing_points:
            return []

        # Busca as stopwords ativas diretamente do banco
        regex_stopwords = self._get_stopwords_regex()

        tags_brutas = indexing_points.split(",")
        tags_limpas = set()

        for tag in tags_brutas:
            tag = tag.strip().lower()

            tag = regex_stopwords.sub("", tag).strip()

            tag = re.sub(r"\s+", " ", tag)

            if 2 < len(tag) <= 100:
                tags_limpas.add(tag)
            elif len(tag) > 100:
                logger.warning(f"⚠️ Tag ignorada por ser muito longa: '{tag[:50]}...'")

        return [
            ArchiveTagDTO(name=tag_name, macro_category_id=None, ai_confidence_score=None) for tag_name in tags_limpas
        ]

    def process_worker_tags(self, dtos_from_worker: list[ArchiveTagDTO]) -> list[int]:
        """
        Pipeline de negócio: Verifica sinônimos e roteia para gravação.
        Retorna a lista final de IDs (canônicos ou recém-criados) para vincular ao documento.
        """
        if not dtos_from_worker:
            return []

        # 1. Extrai apenas os nomes em minúsculas para checar os sinônimos no banco
        names_to_search = [dto.name.strip().lower() for dto in dtos_from_worker]

        # 2. Busca o mapeamento no Repositório (Retorna algo como: {"prefeiruta": 45, "parques": 12})
        mapa_sinonimos = self.repo.get_synonyms_mapping(names_to_search)

        ids_finais_para_o_documento = []
        dtos_para_criar = []

        # 3. O Roteamento de Regra de Negócio (A malha fina)
        for dto in dtos_from_worker:
            nome_normalizado = dto.name.strip().lower()

            if nome_normalizado in mapa_sinonimos:
                # É um sinônimo conhecido! Descartamos a DTO e usamos o ID da Tag Canônica
                id_canonico = mapa_sinonimos[nome_normalizado]
                ids_finais_para_o_documento.append(id_canonico)
            else:
                # É uma tag nova ou legítima. Vai para a fila de persistência.
                dtos_para_criar.append(dto)

        # 4. Envia para o repositório de criação APENAS as tags que não eram sinônimos
        if dtos_para_criar:
            ids_novos_ou_existentes = self.repo.get_or_create_tags(dtos_para_criar)
            ids_finais_para_o_documento.extend(ids_novos_ou_existentes)

        # 5. Retorna um set convertido em lista para garantir que o mesmo documento
        # não receba o mesmo ID de tag duas vezes (ex: se "parque" e "parques" vierem no mesmo documento)
        return list(set(ids_finais_para_o_documento))

    def save_new_stopwords(self, word_list: list[str]) -> int:
        return self.repo.save_stopwords(word_list)

    def purge_stopwords(self) -> int:
        """
        Varre a tabela de tags e apaga graciosamente qualquer tag que bata
        exatamente com a lista oficial de stopwords."""

        stopwords_clean = self.repo.get_stopwords()
        if not stopwords_clean:
            return 0

        return self.repo.purge_tags_by_stopwords(stopwords_clean)

    def get_tag_relevance_count(self, limit: int = 30) -> Sequence[TagRelevanceCount]:
        """
        Conta quantas vezes cada tag aparece associada a um documento no acervo.
        """
        results = self.repo.get_relevance_count(limit)
        return [TagRelevanceCount.model_validate(r) for r in results]

    def get_tag_relevance_tfidf(self, limit: int = 30) -> Sequence[TagRelevanceIdf]:
        """
        Calcula a relevância global das tags usando a fórmula TF-IDF nativa no PostgreSQL.
        Penaliza tags genéricas que aparecem em todo o acervo e destaca termos específicos.
        """
        results = self.repo.get_relevance_tfidf(limit)
        return [TagRelevanceIdf.model_validate(r) for r in results]

    def find_similar_tags(self, target_tag: str, threshold: float = 0.5) -> Sequence[TagSimilarity]:
        """
        Busca tags com erros de digitação ou similaridade alta usando a extensão pg_trgm.
        """
        if not target_tag:
            raise InvalidParam("O parametro 'target_tag' é obrigatório")

        # Regra de negócio: sempre buscar minúsculas
        target_lower = target_tag.strip().lower()
        results = self.repo.find_similar(target_lower, threshold)

        return [TagSimilarity.model_validate(r) for r in results]

    def find_all_similar_tag_pairs(self, threshold: float = 0.65) -> Sequence[TagPairSimilarity]:
        """
        Varre o acervo e cruza todas as tags entre si para encontrar
        pares que sejam muito parecidos (potenciais duplicações).
        """
        results = self.repo.find_all_similar_pairs(threshold)
        return [TagPairSimilarity.model_validate(r) for r in results]

    def merge(self, canonical_id: int, ids_to_merge: list[int]) -> MergeResponse:
        """
        Orquestra a fusão de tags, normalizando sinônimos e delegando a persistência ao Repo.
        """
        if not ids_to_merge:
            raise InvalidParam("A lista de tags para mesclar não pode estar vazia.")

        if canonical_id in ids_to_merge:
            raise InvalidMergeError("O ID da tag canônica não pode estar na lista de exclusão.")

        canonical_exists = self.repo.get_by_id(canonical_id)
        if not canonical_exists:
            raise InvalidParam(f"A tag canônica informada (ID {canonical_id}) não existe no acervo.")

        # 1. Busca nomes das mortas e normaliza para o Worker encontrar depois
        tags_mortas = self.repo.get_by_ids(ids_to_merge)
        nomes_sinonimos = [t.name.strip().lower() for t in tags_mortas]

        # 2. Transfere os vínculos
        docs_brutos = self.repo.get_document_ids_by_tags(ids_to_merge)
        docs_unicos = set(docs_brutos)

        if docs_unicos:
            self.repo.link_documents_to_tag(docs_unicos, canonical_id)

        # 3. Salva Sinônimos
        if nomes_sinonimos:
            sinonimos_data = [
                {
                    "synonym_name": nome,
                    "category": "TAG",
                    "canonical_tag_id": canonical_id,
                    "canonical_entity_id": None,
                }
                for nome in nomes_sinonimos
            ]
            self.repo.create_synonyms(sinonimos_data)

        # 4. Apaga o lixo
        tags_deleted = self.repo.delete_tags(ids_to_merge)

        return MergeResponse(documents_updated=len(docs_unicos), tags_deleted=tags_deleted)

    def get_text_to_suggest_macro_category(
        self,
        source_type: Literal["tags", "documents"] = "tags",
        columns_to_extract: list[str] | None = None,
    ) -> list[str]:
        """
        Extrai todas a tags do acervo e utiliza Inteligência Artificial
        (Clustering) para sugerir agrupamentos semânticos (Macro Categorias).
        """
        logger.info(f"🔍 Iniciando descoberta de tópicos usando source_type:{source_type}...")

        if source_type not in ["tags", "documents"]:
            raise InvalidParam("O parâmetro 'source_type' deve ser obrigatoriamente 'tags' ou 'documents'.")

        if source_type == "tags":
            texts_to_analize = self.repo.fetch_tags_for_clustering()
        elif source_type == "documents":
            # Gambiarra que sera refatorada
            texts_to_analize = self.document_repo.fetch_documents_for_clustering(columns_to_extract=columns_to_extract)

        return texts_to_analize

    # TODO Pensar em como fazer isso. Tirar as entidades conhecidas das tags ou não. Tags precisam ser classiicadas em assuntos.
    def purge_entities_from_tags(self):
        pass

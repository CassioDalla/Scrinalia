from collections.abc import Sequence
from typing import Literal

from domains.archive.exceptions import InvalidMergeError, InvalidParam
from domains.archive.repository.entity_repo import EntityRepository
from domains.archive.schemas.entity_schema import (
    EntityMergeResponse,
    EntityPairSimilarity,
    EntityRelevance,
    EntitySimilarity,
)


class EntityService:
    """
    Serviço de domínio responsável por auditar, higienizar e unificar
    entidades nomeadas (Pessoas, Organizações, Locais) no acervo.
    """

    def __init__(self, repo: EntityRepository):
        self.repo = repo

    def find_similar(
        self, target_name: str, entity_type: Literal["ORG", "PER", "LOC"] | None = None, threshold: float = 0.5
    ) -> Sequence[EntitySimilarity]:
        if not target_name:
            raise InvalidParam("O parâmetro 'target_name' é obrigatório.")

        # Regra de negócio: a busca deve ser sempre enviada em minúsculas
        target_lower = target_name.strip().lower()

        results = self.repo.find_similar(target_lower, entity_type, threshold)

        return [EntitySimilarity.model_validate(r) for r in results]

    def find_all_similar_entity_pairs(self, threshold: float = 0.65) -> Sequence[EntityPairSimilarity]:

        results = self.repo.find_all_similar_pairs(threshold)

        return [
            EntityPairSimilarity(
                id_1=r.id_1,
                name_1=r.name_1,
                type_1=r.type_1,
                id_2=r.id_2,
                name_2=r.name_2,
                type_2=r.type_2,
                similarity=r.similarity,
            )
            for r in results
        ]

    def merge(self, canonical_id: int, ids_to_merge: list[int]) -> EntityMergeResponse:
        """
        Orquestra a fusão de entidades aplicando regras de negócio e sanitização.
        """
        # Regra 1: Blindagem contra auto-mesclagem
        if canonical_id in ids_to_merge:
            raise InvalidMergeError("O ID da entidade canônica não pode estar na lista de exclusão.")

        if not ids_to_merge:
            raise InvalidParam("A lista de entidades para mesclar não pode estar vazia.")

        # Regra 2: Valida se a canônica existe para herdar a tipagem
        canonical = self.repo.get_by_id(canonical_id)
        if not canonical:
            raise InvalidParam(f"Entidade canônica com ID {canonical_id} não encontrada.")

        # Regra 3: Higienização de dados (Nomes para sinônimos devem ser minúsculos)
        dead_entities = self.repo.get_by_ids(ids_to_merge)
        synonym_name = [e.name.strip().lower() for e in dead_entities]

        # Coordenação 1: Transferir documentos
        docs_brutos = self.repo.get_document_ids_by_entities(ids_to_merge)
        docs_unicos = set(docs_brutos)
        if docs_unicos:
            self.repo.link_documents_to_entity(docs_unicos, canonical_id)

        # Coordenação 2: Gravar sinônimos
        if synonym_name:
            synonyms_data = [
                {
                    "synonym_name": nome,
                    "category": canonical.entity_type,
                    "canonical_tag_id": None,
                    "canonical_entity_id": canonical_id,
                }
                for nome in synonym_name
            ]
            self.repo.create_synonyms(synonyms_data)

        # Coordenação 3: Apagar entidades velhas
        linhas_apagadas = self.repo.delete_entities(ids_to_merge)

        return EntityMergeResponse(documents_updated=len(docs_unicos), entities_deleted=linhas_apagadas)

    def get_entity_relevance_count(
        self, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> Sequence[EntityRelevance]:
        """
        Conta a relevância das entidades filtrando pelo tipo opcionalmente.
        Mapeia os resultados do repositório para o DTO puro de Domínio.
        """
        results = self.repo.get_relevance_count(entity_type, limit)

        return [EntityRelevance.model_validate(r) for r in results]

    def purge_orphan_entities(self) -> int:
        """
        Varre e apaga entidades que ficaram órfãs (sem documentos vinculados)
        após curadorias humanas ou exclusões de documentos no sistema.
        """
        return self.repo.purge_orphan_entities()

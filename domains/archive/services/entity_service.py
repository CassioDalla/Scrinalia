from collections.abc import Sequence
from typing import Literal

from domains.archive.exceptions import InvalidParam
from domains.archive.repository.entity_repo import EntityRepository
from domains.archive.schemas.entity_schema import (
    ConflictResolutionData,
    CrossDomainConflict,
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

    def merge(self, canonical_id: int, ids_to_merge: list[int], new_name: str | None = None) -> EntityMergeResponse:
        """
        Orquestra a fusão de entidades aplicando regras de negócio e sanitização.
        Permite renomear a entidade canônica
        """

        # Regra 1: Blindagem contra auto-mesclagem
        ids_reais = [id_ for id_ in ids_to_merge if id_ != canonical_id]

        # Se não há fusão e não há renomeação, ignora.
        if not ids_reais and not new_name:
            return EntityMergeResponse(documents_updated=0, entities_deleted=0)

        # Regra 2: Valida se a canônica existe para herdar a tipagem
        canonical = self.repo.get_by_id(canonical_id)
        if not canonical:
            raise InvalidParam(f"Entidade canônica com ID {canonical_id} não encontrada.")

        # Regra 3: Higienização de dados (Nomes para sinônimos devem ser minúsculos)
        dead_entities = self.repo.get_by_ids(ids_reais) if ids_reais else []
        synonym_name = [e.name.strip().lower() for e in dead_entities]

        # Coordenação 0: Renomeação da Entidade Canônica
        if new_name and new_name.strip() and new_name.strip().lower() != canonical.name.lower():
            old_name = canonical.name
            # Adiciona o nome antigo como sinônimo para não quebrar buscas futuras
            synonym_name.append(old_name.strip().lower())
            self.repo.update_entity_name(canonical_id, new_name.strip())

        # Coordenação 1: Transferir documentos
        docs_unicos = set()
        if ids_reais:
            docs_brutos = self.repo.get_document_ids_by_entities(ids_reais)
            docs_unicos = set(docs_brutos)
            if docs_unicos:
                self.repo.link_documents_to_entity(docs_unicos, canonical_id)

        # Coordenação 2: Gravar sinônimos (Tanto das entidades mortas quanto o nome antigo)
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
        linhas_apagadas = 0
        if ids_reais:
            linhas_apagadas = self.repo.delete_entities(ids_reais)

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

    def reclassify_entity(self, entity_id: int, new_type: Literal["ORG", "PER", "LOC"]) -> None:
        """
        Corrige a classificação de uma entidade e cria uma âncora (sinônimo)
        para prevenir falsos positivos futuros do Worker NER.
        """
        canonical = self.repo.get_by_id(entity_id)
        if not canonical:
            raise InvalidParam(f"Entidade canônica com ID {entity_id} não encontrada.")

        if canonical.entity_type == new_type:
            raise InvalidParam(f"A entidade '{canonical.name}' já está classificada como {new_type}.")

        self.repo.update_entity_type(entity_id, new_type)

        # 2. Gera o sinônimo de ancoragem (em minúsculas, como definimos nas regras de negócio)
        synonym_data = [
            {
                "synonym_name": canonical.name.strip().lower(),
                "category": new_type,
                "canonical_tag_id": None,
                "canonical_entity_id": entity_id,
            }
        ]

        self.repo.create_synonyms(synonym_data)

    def purge_entity_stopwords(self, words: list[str]) -> int:
        """
        Adiciona termos à lista negra de extração do NER e varre o banco
        para expurgar entidades falsas que já tenham sido criadas.
        """
        if not words:
            return 0

        # 1. Grava na lista negra (Worker não vai extrair mais)
        self.repo.save_entity_stopwords(words)

        # 2. Expurga o passado (Limpa a base atual)
        linhas_apagadas = self.repo.delete_entities_by_names(words)

        return linhas_apagadas

    def delete_entity(self, entity_id: int) -> None:
        """Exclui cirurgicamente uma entidade isolada do banco de dados."""
        entity = self.repo.get_by_id(entity_id)
        if not entity:
            raise InvalidParam(f"Entidade com ID {entity_id} não encontrada para exclusão.")

        self.repo.delete_entities([entity_id])

    def find_cross_domain_conflicts(self, threshold: float = 0.85) -> Sequence[CrossDomainConflict]:
        """Varre o banco procurando Tags e Entidades que possuem o mesmo nome ou grafia muito próxima."""
        results = self.repo.get_cross_domain_conflicts(threshold)
        return [CrossDomainConflict.model_validate(dict(r._mapping)) for r in results]

    def resolve_cross_domain_conflict(
        self, winner: Literal["TAG", "ENTITY"], tag_id: int, entity_id: int
    ) -> ConflictResolutionData:
        """Resolve o conflito transferindo os relacionamentos para o vencedor e expurgando o perdedor."""
        if winner not in ["TAG", "ENTITY"]:
            raise InvalidParam("O vencedor (winner) deve ser obrigatoriamente 'TAG' ou 'ENTITY'.")

        docs_transferidos = self.repo.resolve_cross_domain_conflict(winner, tag_id, entity_id)

        return ConflictResolutionData(winner=winner, documents_transferred=docs_transferidos)

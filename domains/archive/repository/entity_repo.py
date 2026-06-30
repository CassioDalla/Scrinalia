from collections.abc import Sequence
from typing import Literal, cast

from sqlalchemy import CursorResult, Row, delete, desc, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from domains.archive.exceptions import InvalidParam
from domains.archive.models import ArchiveDocumentEntity, ArchiveEntity, DomainStopwords, DomainSynonyms, StopwordsScope
from domains.archive.schemas.entity_schema import ArchiveEntityDTO


class EntityRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, entity_id: int) -> ArchiveEntity | None:
        return self.db.scalar(select(ArchiveEntity).where(ArchiveEntity.entity_id == entity_id))

    def get_by_ids(self, entity_ids: list[int]) -> Sequence[ArchiveEntity]:
        if not entity_ids:
            return []
        return self.db.scalars(select(ArchiveEntity).where(ArchiveEntity.entity_id.in_(entity_ids))).all()

    def find_similar(
        self, target_name: str, entity_type: Literal["ORG", "PER", "LOC"] | None = None, threshold: float = 0.5
    ) -> Sequence[Row]:
        """
        Busca entidades com erros de digitação ou similaridade alta usando a extensão pg_trgm.
        Retorna também o 'entity_type' para ajudar o usuário a decidir se a mesclagem faz sentido.
        """

        if not target_name:
            raise InvalidParam("O parametro 'target_tag'é obrigatório")

        self.db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold}"))

        target_lower = target_name.lower()
        similaridade = func.similarity(ArchiveEntity.name, target_lower)

        stmt = (
            select(
                ArchiveEntity.entity_id, ArchiveEntity.name, ArchiveEntity.entity_type, similaridade.label("similarity")
            )
            .where(ArchiveEntity.name.op("%")(target_lower))
            .where(func.lower(ArchiveEntity.name) != target_lower)
        )

        if entity_type:
            stmt = stmt.where(ArchiveEntity.entity_type == entity_type)

        stmt = stmt.order_by(desc("similarity")).limit(15)

        return self.db.execute(stmt).fetchall()

    def find_all_similar_pairs(self, threshold: float = 0.65) -> Sequence[Row]:
        """
        Varre o acervo e cruza todas as entidades entre si para encontrar
        pares que sejam muito parecidos (potenciais duplicações ou erros do NER).
        """
        # 1. Configura o threshold nativo do PostgreSQL apenas para esta transação.
        self.db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold}"))

        # Cria os alias para o Self Join
        Entity1 = aliased(ArchiveEntity)
        Entity2 = aliased(ArchiveEntity)

        # Prepara o cálculo de similaridade
        similaridade = func.similarity(Entity1.name, Entity2.name)

        stmt = (
            select(
                Entity1.entity_id.label("id_1"),
                Entity1.name.label("name_1"),
                Entity1.entity_type.label("type_1"),
                Entity2.entity_id.label("id_2"),
                Entity2.name.label("name_2"),
                Entity2.entity_type.label("type_2"),
                similaridade.label("similarity"),
            )
            # O Join garantindo que só testa combinações únicas (A com B) e ignora espelhadas (B com A)
            .join(Entity2, Entity1.entity_id < Entity2.entity_id)
            # 2. HACK DE PERFORMANCE: Só compara entidades que tenham até 3 letras de diferença no tamanho
            .where(func.abs(func.length(Entity1.name) - func.length(Entity2.name)) <= 3)
            # 3. O SEGREDO: O operador % é a única coisa que ativa o Índice GIN!
            .where(Entity1.name.op("%")(Entity2.name))
            .order_by(desc("similarity"), Entity1.name)
        )

        return self.db.execute(stmt).all()

    # --- Métodos de Ingestão e NER ---

    def get_ner_synonyms_rules(self) -> list[dict]:
        """
        Carrega as regras de normalização semântica exclusivas para o pipeline de NER (spaCy).
        Ignora sinônimos de TAGs, retornando apenas mapeamentos para Entidades Canônicas.
        """

        stmt = (
            select(DomainSynonyms.synonym_name, DomainSynonyms.category, ArchiveEntity.name.label("canonical_entity"))
            .join(ArchiveEntity, DomainSynonyms.canonical_entity_id == ArchiveEntity.entity_id)
            .where(DomainSynonyms.category.in_(["ORG", "LOC", "PER"]))
        )

        results = self.db.execute(stmt).all()

        return [
            {"pattern": row.synonym_name, "label": row.category, "canonical_name": row.canonical_entity}
            for row in results
        ]

    def get_or_create_entities(self, entities_list: list[ArchiveEntityDTO]) -> list[int]:
        """
        Gerencia a dimensão de entidades (NER).

        Recebe uma lista de Pessoas, Organizações ou Locais identificados pela IA.
        Utiliza ON CONFLICT DO NOTHING para garantir a unicidade pelo nome.

        Returns:
            list[int]: Lista de IDs (Chaves Primárias) das entidades prontas para vínculo.
        """

        if not entities_list:
            return []

        # 1. Prepara a lista de dicionários para o INSERT massivo
        insert_data = []
        names_to_search = []

        for ent in entities_list:
            name_clean = ent.name.strip()
            names_to_search.append(name_clean)
            insert_data.append({"name": name_clean, "entity_type": ent.entity_type})

        # 2. Faz o INSERT massivo ignorando as entidades que já existem (índice único no 'name')
        stmt_insert = insert(ArchiveEntity).values(insert_data).on_conflict_do_nothing(index_elements=["name"])
        self.db.execute(stmt_insert)

        # 3. Num ÚNICO select, busca todos os IDs (dos que acabaram de ser criados e dos já existentes)
        stmt_select = select(ArchiveEntity.entity_id).where(ArchiveEntity.name.in_(names_to_search))

        return list(self.db.scalars(stmt_select).all())

    # --- Métodos para o Merge ---

    def get_document_ids_by_entities(self, entity_ids: list[int]) -> Sequence[str]:
        stmt = select(ArchiveDocumentEntity.description_id).where(ArchiveDocumentEntity.entity_id.in_(entity_ids))
        return self.db.scalars(stmt).all()

    def link_documents_to_entity(self, doc_ids: set[str], target_entity_id: int) -> None:
        novos_vinculos = [{"description_id": doc_id, "entity_id": target_entity_id} for doc_id in doc_ids]
        stmt = insert(ArchiveDocumentEntity).values(novos_vinculos).on_conflict_do_nothing()
        self.db.execute(stmt)

    def link_entities_to_document(self, description_id: str, entity_ids: list[int]) -> None:
        """Vincula múltiplas entidades a um único documento (Usado na Ingestão / Worker)."""
        if not entity_ids:
            return

        # Usamos set(entity_ids) para evitar tentar inserir a mesma entidade duas vezes no mesmo documento
        novos_vinculos = [{"description_id": description_id, "entity_id": e_id} for e_id in set(entity_ids)]
        stmt = insert(ArchiveDocumentEntity).values(novos_vinculos).on_conflict_do_nothing()
        self.db.execute(stmt)

    def bulk_link_entities(self, links_data: list[dict]) -> None:
        """
        Otimização para Ingestão em Lote (Workers).
        Insere milhares de vínculos N:N numa única transação.
        Recebe: [{"description_id": "doc1", "entity_id": 1}, ...]
        """
        if not links_data:
            return

        # Converte para tuplas e depois para dict novamente para remover duplicidades
        # exatas enviadas no mesmo lote, prevenindo trancamentos desnecessários (locks)
        unique_links = [dict(t) for t in {tuple(d.items()) for d in links_data}]

        stmt = insert(ArchiveDocumentEntity).values(unique_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def create_synonyms(self, synonyms_data: list[dict]) -> None:
        stmt = insert(DomainSynonyms).values(synonyms_data).on_conflict_do_nothing()
        self.db.execute(stmt)

    def delete_entities(self, entity_ids: list[int]) -> int:
        # A deleção associativa (ArchiveDocumentEntity) fica aqui também
        self.db.execute(delete(ArchiveDocumentEntity).where(ArchiveDocumentEntity.entity_id.in_(entity_ids)))

        result = self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id.in_(entity_ids)))
        return cast(CursorResult, result).rowcount

    def update_entity_type(self, entity_id: int, new_type: str) -> None:
        """Atualiza a categoria (PER, LOC, ORG) de uma entidade canônica."""
        # Ajuste 'Entity' para o nome exato da sua classe de Modelo SQLAlchemy
        entity = self.db.query(ArchiveEntity).filter(ArchiveEntity.entity_id == entity_id).first()
        if entity:
            entity.entity_type = new_type

    def update_entity_name(self, entity_id: int, new_name: str) -> None:
        entity = self.db.query(ArchiveEntity).filter(ArchiveEntity.entity_id == entity_id).first()
        if entity:
            entity.name = new_name

    def save_entity_stopwords(self, words: list[str]) -> None:
        """Salva as palavras na lista negra com o escopo exclusivo para Entidades."""
        for word in words:
            clean_word = word.strip().lower()

            # Verifica se já não existe para evitar erro de Unique Constraint
            exists = self.db.query(DomainStopwords).filter_by(word=clean_word, word_scope=StopwordsScope.ENTITY).first()

            if not exists:
                new_stopword = DomainStopwords(word=clean_word, word_scope=StopwordsScope.ENTITY)
                self.db.add(new_stopword)

    def delete_entities_by_names(self, names: list[str]) -> int:
        """Deleta entidades do acervo buscando por uma lista de nomes exatos."""
        clean_names = [n.strip().lower() for n in names]

        linhas_apagadas = (
            self.db.query(ArchiveEntity)
            .filter(func.lower(ArchiveEntity.name).in_(clean_names))
            .delete(synchronize_session=False)
        )

        return linhas_apagadas

    # --- Consultas Analíticas e Manutenção ---

    def get_relevance_count(
        self, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> Sequence[Row]:
        """Busca as entidades mais referenciadas em documentos."""
        stmt = select(
            ArchiveEntity.entity_id,
            ArchiveEntity.name,
            ArchiveEntity.entity_type,
            func.count(ArchiveDocumentEntity.description_id).label("total_usage"),
        ).join(ArchiveDocumentEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)

        if entity_type:
            stmt = stmt.where(ArchiveEntity.entity_type == entity_type)

        stmt = stmt.group_by(ArchiveEntity.entity_id).order_by(desc("total_usage")).limit(limit)
        return self.db.execute(stmt).all()

    def purge_orphan_entities(self) -> int:
        """Encontra e apaga entidades que não possuem nenhum documento vinculado."""
        stmt_orphans = (
            select(ArchiveEntity.entity_id)
            .outerjoin(ArchiveDocumentEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)
            .where(ArchiveDocumentEntity.description_id.is_(None))
        )

        orphans = self.db.scalars(stmt_orphans).all()

        if not orphans:
            return 0

        resultado = self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id.in_(orphans)))
        return cast(CursorResult, resultado).rowcount

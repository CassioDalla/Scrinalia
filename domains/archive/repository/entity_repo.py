from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from domains.archive.models import (
    ArchiveEntity,
    DomainSynonyms,
)
from domains.archive.schemas.schemas import ArchiveEntityDTO

def get_ner_synonyms_rules(db: Session):
    """
    Carrega as regras de normalização semântica exclusivas para o pipeline de NER (spaCy).
    Ignora sinônimos de TAGs, retornando apenas mapeamentos para Entidades Canônicas.
    """

    stmt = (
        select(DomainSynonyms.synonym_name, DomainSynonyms.category, ArchiveEntity.name.label("canonical_entity"))
        .join(ArchiveEntity, DomainSynonyms.canonical_entity_id == ArchiveEntity.entity_id)
        .where(DomainSynonyms.category.in_(["ORG", "LOC", "PER"]))
    )

    results = db.execute(stmt).all()

    return [
        {"pattern": row.synonym_name, "label": row.category, "canonical_name": row.canonical_entity} for row in results
    ]

def get_or_create_entities(db: Session, entities_list: list[ArchiveEntityDTO]) -> list[int]:
    """
    Gerencia a dimensão de entidades (NER).

    Recebe uma lista de Pessoas, Organizações ou Locais identificados pela IA.
    Utiliza ON CONFLICT DO NOTHING para garantir a unicidade pelo nome.

    Returns:
        list[int]: Lista de IDs (Chaves Primárias) das entidades prontas para vínculo.
    """
    if not entities_list:
        return []

    entity_ids = []
    for ent in entities_list:
        name_clean = ent.name.strip()

        stmt = (
            insert(ArchiveEntity)
            .values(name=name_clean, entity_type=ent.entity_type)
            .on_conflict_do_nothing(index_elements=["name"])
        )

        db.execute(stmt)

        # Busca o ID (seja ele recém-criado ou já existente)
        id_query = select(ArchiveEntity.entity_id).where(ArchiveEntity.name == name_clean)
        entity_id = db.execute(id_query).scalar_one()
        entity_ids.append(entity_id)

    return entity_ids

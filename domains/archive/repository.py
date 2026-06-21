import re
from typing import cast

from sqlalchemy import CursorResult, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTypology,
    DomainStopwords,
    DomainSynonyms,
)
from domains.archive.schemas.schemas import ArchiveDocumentDTO, ArchiveEntityDTO, ArchiveTagDTO

"""Como resolvemos isso elegantemente?
Não mexemos no upsert de transferência da Staging. Nós delegamos isso para os Workers de IA!

Quando formos criar o worker_ner.py (que extrai pessoas/locais), a primeira coisa que a função dele vai fazer no banco de dados será: "Delete todas as entidades antigas vinculadas a este description_id, e insira as novas que acabei de encontrar".
"""


def upsert_archive_document(db: Session, doc_data: ArchiveDocumentDTO) -> bool:
    """
    Insere ou atualiza o documento fato na camada Archive a partir dos dados da Staging.

    ⚠️ RESTRIÇÃO CRÍTICA DE ARQUITETURA (USO EXCLUSIVO EM CARGA/MIGRAÇÃO):
    Esta função foi projetada UNICAMENTE para o pipeline de transferência Staging -> Archive.
    O UPDATE só será executado se o 'staging_content_hash' que está a chegar
    for DIFERENTE do hash atualmente persistido na Archive (mudança na origem).

    🚨 IMPORTANTE PARA PIPELINES DE IA (WORKERS):
    NÃO utilize esta função para salvar enriquecimentos de IA (spaCy, mDeBERTa).
    Para os Workers, utilize funções cirúrgicas de UPDATE (como o stamp_ai_execution),
    caso contrário, o ON CONFLICT bloqueará a operação e descartará os dados da IA.

    🔒 GOVERNANÇA (HUMAN-IN-THE-LOOP):
    Se o documento possuir o status 'HUMAN_APPROVED', o PostgreSQL bloqueará
    qualquer tentativa de sobrescrita, blindando a revisão humana de retrocessos.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        doc_data (ArchiveDocumentDTO): Objeto validado com metadados ISAD(G).

    Returns:
        bool: True se o registro foi criado ou modificado; False se a operação foi
              ignorada por consistência de Hash ou por proteção ao trabalho humano.
    """
    db_dict = doc_data.model_dump(exclude_unset=True)

    stmt = insert(ArchiveDocument).values(db_dict)

    # Protege colunas imutáveis ou que são de responsabilidade exclusiva da Archive.
    protected_columns = [
        "description_id",  # PK (Nunca muda)
        "created_at",  # Data de criação (Nunca muda)
        "storage_thumbnail_uri",  # Gerado pelo Storage
    ]

    update_dict = {col.name: col for col in stmt.excluded if col.name not in protected_columns}
    # Só faz o UPDATE se o status atual no banco NÃO for HUMAN_APPROVED
    stmt = stmt.on_conflict_do_update(
        index_elements=["description_id"],
        set_=update_dict,
        where=(
            (ArchiveDocument.review_status != ArchiveReviewStatus.HUMAN_APPROVED)
            & (ArchiveDocument.staging_content_hash != stmt.excluded.staging_content_hash)
        ),
    )
    stmt = stmt.returning(ArchiveDocument.description_id)

    saved_id = db.scalar(stmt)
    return saved_id is not None


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


def get_or_create_tags(db: Session, tags_list: list[ArchiveTagDTO]) -> list[int]:
    """
    Gerencia a dimensão de tags e taxonomias do mDeBERTa.
    Garante que termos idênticos (em minúsculas) partilhem o mesmo ID no banco.
    """

    if not tags_list:
        return []

    tag_ids = []
    for t in tags_list:
        # Tags oficiais sempre minúsculas para agrupamento perfeito (ex: alvenaria)
        name_clean = t.name.strip().lower()

        stmt = (
            insert(ArchiveTag)
            .values(
                name=name_clean,
                macro_category_id=t.macro_category_id,
                ai_confidence_score=t.ai_confidence_score,
            )
            .on_conflict_do_nothing(index_elements=["name"])
        )

        db.execute(stmt)

        id_query = select(ArchiveTag.tag_id).where(ArchiveTag.name == name_clean)
        tag_id = db.execute(id_query).scalar_one()
        tag_ids.append(tag_id)

    return tag_ids


def link_description_relationships(db: Session, description_id: str, entity_ids: list[int], tag_ids: list[int]) -> None:
    """
    Cria as pontes relacionais N:N de forma otimizada (Bulk Insert).
    Utiliza ON CONFLICT DO NOTHING para evitar erros de chave duplicada no reprocessamento.
    """

    if entity_ids:
        entity_payload = [{"description_id": description_id, "entity_id": eid} for eid in entity_ids]
        stmt_ent = insert(ArchiveDocumentEntity).values(entity_payload).on_conflict_do_nothing()
        db.execute(stmt_ent)

    if tag_ids:
        tag_payload = [{"description_id": description_id, "tag_id": tid} for tid in tag_ids]
        stmt_tag = insert(ArchiveDocumentTag).values(tag_payload).on_conflict_do_nothing()
        db.execute(stmt_tag)


def stamp_ai_execution(db: Session, description_id: str, worker_name: str) -> None:
    """
    Carimba o documento com a assinatura do Worker de IA que terminou o processo.
    Isto evita que a IA refaça o mesmo trabalho caso o servidor reinicie.
    """
    stmt = select(ArchiveDocument).where(ArchiveDocument.description_id == description_id)
    doc = db.execute(stmt).scalar_one_or_none()

    if doc:
        new_log = dict(doc.execution_log)
        new_log[worker_name] = "DONE"

        # Substitui e avisa o SQLAlchemy que o JSON foi modificado
        doc.execution_log = new_log
        flag_modified(doc, "execution_log")


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


def save_stopwords(db: Session, words_list: list[str]) -> int:
    """
    Insere uma lista de palavras na tabela de stopwords em lote.
    Retorna a quantidade exata de novas stopwords inseridas.
    """
    if not words_list:
        return 0

    clean_words = [{"word": w.strip().lower()} for w in words_list if w.strip()]

    if not clean_words:
        return 0

    stmt = insert(DomainStopwords).values(clean_words).on_conflict_do_nothing()

    result = cast(CursorResult, db.execute(stmt))
    return result.rowcount


def get_stopwords(db: Session) -> set[str]:
    """
    Recupera todas as stopwords de domínio cadastradas no banco de dados.
    Retorna um conjunto (Set) de stopwords

    Args:
        db (Session): Sessão ativa do SQLAlchemy.

    Returns:
        set[str]: Conjunto contendo todas as stopwords em letras minúsculas.
    """
    stmt = select(DomainStopwords.word)
    results = db.scalars(stmt).all()
    return set(results)


def get_active_typologies(db: Session) -> dict[str, int]:
    """
    Recupera todas as tipologias de documentos cadastradas no banco de dados.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.

    Returns:
        dict[str, int]: Dicionário contendo nome+contexto e id ex {"Fotografia": 1}.
    """

    stmt = select(ArchiveTypology.typology_id, ArchiveTypology.name, ArchiveTypology.context_description)

    results = db.execute(stmt).all()

    typologies_map = {}
    for typo_id, name, description in results:
        # Cria uma label  descritiva para a IA
        # Ex: "Planta Arquitetônica: Projetos de aumento, construção e reformas."
        context_label = f"{name}: {description}" if description else name

        typologies_map[context_label] = typo_id

    return typologies_map


def fetch_tags_for_clustering(db: Session) -> list[str]:
    """Busca apenas tags únicas que ainda não têm Macro Categoria."""
    stmt = select(ArchiveTag.name).where(ArchiveTag.macro_category_id.is_(None)).distinct()
    results = db.scalars(stmt).all()

    texts = [t for t in results if t and not t.replace(".", "").isdigit()]
    return texts


def fetch_documents_for_clustering(db: Session, columns_to_extract: list[str] | None = None) -> list[str]:
    """
    Busca documentos e concatena as colunas textuais solicitadas
    numa única string coesa para alimentar a IA.
    """
    columns = columns_to_extract or ["original_title", "admin_bio_history", "provenance", "scope_content"]

    filters = [getattr(ArchiveDocument, col).is_not(None) for col in columns]
    stmt = select(ArchiveDocument).where(or_(*filters))

    docs = db.scalars(stmt).all()
    clean_txt = []

    for doc in docs:
        parts = []
        for col in columns:
            val = getattr(doc, col)
            # Garante que não é nulo, é string e não está vazia (só espaços)
            if val and isinstance(val, str) and val.strip():
                # Remove quebras de linha para não confundir o algoritmo
                texto_limpo = re.sub(r"\s+", " ", val.strip())
                if texto_limpo:
                    parts.append(texto_limpo)

        if parts:
            # Junta o Título com a Descrição usando um ponto e espaço
            clean_txt.append(". ".join(parts) + ".")

    return clean_txt

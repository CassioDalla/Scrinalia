from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.models.gold_layer import (
    DomainStopwordsModel,
    GoldDescriptionEntityModel,
    GoldDescriptionModel,
    GoldDescriptionTagModel,
    GoldEntityModel,
    GoldReviewStatus,
    GoldTagModel,
)
from core.schemas.gold_schema import GoldDescriptionDTO, GoldEntityDTO, GoldTagDTO


def upsert_gold_description(db: Session, doc_data: GoldDescriptionDTO) -> bool:
    """
    Insere ou atualiza o documento fato na Camada Ouro a partir dos dados da Silver.

    ⚠️ RESTRIÇÃO CRÍTICA DE ARQUITETURA (USO EXCLUSIVO EM CARGA/MIGRAÇÃO):
    Esta função foi projetada UNICAMENTE para o pipeline de sincronização Silver -> Gold
    (ex: script `worker_load_gold.py`). Devido à trava de idempotência implementada no
    PostgreSQL, o UPDATE só será executado se o 'silver_content_hash' que está chegando
    for DIFERENTE do hash atualmente persistido na Ouro.

    🚨 IMPORTANTE PARA PIPELINES DE IA (WORKERS):
    NÃO utilize esta função para salvar enriquecimentos de IA (spaCy, Ollama, mDeBERTa).
    Como os modelos de IA não alteram os metadados brutos da Silver, o hash enviado seria
    idêntico ao do banco, fazendo com que a cláusula WHERE do ON CONFLICT bloqueie a
    operação silenciosamente, descartando o final_title, anomaly_reasons, etc.
    Para os Workers, utilize funções cirúrgicas de UPDATE.

    🔒 GOVERNANÇA (HUMAN-IN-THE-LOOP):
    Se o documento na Ouro já possuir o status 'HUMAN_APPROVED', o PostgreSQL bloqueará
    qualquer tentativa de sobrescrita vinda da Silver, blindando a revisão humana de
    retrocessos.

    Args:
        db: Sessão ativa do SQLAlchemy.
        doc_data: DTO validado com metadados ISAD(G) e hash de controle.

    Returns:
        bool: True se o registro foi criado ou modificado; False se a operação foi
              ignorada por consistência de Hash ou por proteção ao trabalho Humano.
    """
    db_dict = doc_data.model_dump(exclude_unset=True)

    # Prepara o insert nativo do Postgres
    stmt = insert(GoldDescriptionModel).values(db_dict)

    update_dict = {
        "original_title": stmt.excluded.original_title,
        "document_date": stmt.excluded.document_date,
        "summary": stmt.excluded.summary,
        "silver_content_hash": stmt.excluded.silver_content_hash,
        # --- Metadados ISAD(G) ---
        "reference_code": stmt.excluded.reference_code,
        "level": stmt.excluded.level,
        "producers": stmt.excluded.producers,
        "admin_bio_history": stmt.excluded.admin_bio_history,
        "admin_archival_history": stmt.excluded.admin_archival_history,
        "provenance": stmt.excluded.provenance,
        "scope_content": stmt.excluded.scope_content,
        "language_name": stmt.excluded.language_name,
        "archivist_notes": stmt.excluded.archivist_notes,
        # --- Reset de IA e Governança ---
        "final_title": stmt.excluded.final_title,
        "semantic_search_vector": stmt.excluded.semantic_search_vector,
        "review_status": stmt.excluded.review_status,
        "is_anomaly": stmt.excluded.is_anomaly,
        "anomaly_reasons": stmt.excluded.anomaly_reasons,
        "execution_log": stmt.excluded.execution_log,
    }

    # Só faz o UPDATE se o status atual no banco NÃO for HUMAN_APPROVED
    stmt = stmt.on_conflict_do_update(
        index_elements=["description_id"],
        set_=update_dict,
        where=(
            (GoldDescriptionModel.review_status != GoldReviewStatus.HUMAN_APPROVED)
            & (GoldDescriptionModel.silver_content_hash != stmt.excluded.silver_content_hash)
        ),
    )
    stmt = stmt.returning(GoldDescriptionModel.description_id)

    saved_id = db.scalar(stmt)
    return saved_id is not None


def get_or_create_entities(db: Session, entities_list: list[GoldEntityDTO]) -> list[int]:
    """
    Gerencia a dimensão de entidades. Recebe uma lista de dicionários contendo
    Pessoas, Organizações ou Locais identificados pela IA ou criados manualmente.

    Garante a unicidade pelo nome da entidade.

    Returns:
        list[int]: Lista de IDs das entidades prontas para serem vinculadas.
    """
    if not entities_list:
        return []

    entity_ids = []
    for ent in entities_list:
        # Força a capitalização limpa (ex: Eduardo Fernando Chaves)
        name_clean = ent.name.strip()

        # ON CONFLICT DO NOTHING garante que se a entidade já existe, o banco não quebra
        stmt = (
            insert(GoldEntityModel)
            .values(name=name_clean, entity_type=ent.entity_type)
            .on_conflict_do_nothing(index_elements=["name"])
        )

        db.execute(stmt)

        # Busca o ID (seja ele recém-criado ou já existente)
        # Como o processo de IA roda em lotes, um SELECT simples por loop aqui é seguro
        id_query = select(GoldEntityModel.entity_id).where(GoldEntityModel.name == name_clean)
        entity_id = db.execute(id_query).scalar_one()
        entity_ids.append(entity_id)

    return entity_ids


def get_or_create_tags(db: Session, tags_list: list[GoldTagDTO]) -> list[int]:
    """
    Gerencia a dimensão de tags e taxonomias de agrupamento do mDeBERTa.
    Garante que termos idênticos compartilhem o mesmo ID.
    """
    if not tags_list:
        return []

    tag_ids = []
    for t in tags_list:
        # Tags oficiais sempre minúsculas para agrupamento perfeito (ex: alvenaria)
        name_clean = t.name.strip().lower()

        stmt = (
            insert(GoldTagModel)
            .values(
                name=name_clean,
                macro_category=t.macro_category,
                ai_confidence_score=t.ai_confidence_score,
            )
            .on_conflict_do_nothing(index_elements=["name"])
        )

        db.execute(stmt)

        id_query = select(GoldTagModel.tag_id).where(GoldTagModel.name == name_clean)
        tag_id = db.execute(id_query).scalar_one()
        tag_ids.append(tag_id)

    return tag_ids


def link_description_relationships(db: Session, description_id: str, entity_ids: list[int], tag_ids: list[int]) -> None:
    """
    Cria as pontes relacionais N:N nas tabelas associativas.
    Usa ON CONFLICT DO NOTHING para permitir reprocessamento sem duplicar vínculos.
    """
    # 1. Vincula Entidades
    for e_id in entity_ids:
        stmt_ent = (
            insert(GoldDescriptionEntityModel)
            .values(description_id=description_id, entity_id=e_id)
            .on_conflict_do_nothing()
        )
        db.execute(stmt_ent)

    # 2. Vincula Tags
    for t_id in tag_ids:
        stmt_tag = (
            insert(GoldDescriptionTagModel).values(description_id=description_id, tag_id=t_id).on_conflict_do_nothing()
        )
        db.execute(stmt_tag)


def stamp_ai_execution(db: Session, description_id: str, worker_name: str) -> None:
    """
    Atualiza apenas o JSONB de log de execução, avisando que um pipeline de IA terminou.
    """
    doc = db.query(GoldDescriptionModel).filter_by(description_id=description_id).first()
    if doc:
        new_log = dict(doc.execution_log)
        new_log[worker_name] = "completed"

        # Substitui e avisa o SQLAlchemy que o JSON foi modificado
        doc.execution_log = new_log
        flag_modified(doc, "execution_log")


def load_nlp_rules(db: Session):
    rules = []

    # Puxa todas as regras da tabela
    results = db.execute(text("SELECT pattern, label, canonical_name FROM nlp_dictionary")).fetchall()

    for line in results:
        rules.append({"pattern": line.pattern, "label": line.label, "id": line.canonical_name})

    return rules


def save_stopwords(db: Session, words_list: list[str]) -> None:
    """
    Insere uma lista de palavras na tabela de stopwords do domínio.

    Utiliza uma operação de Bulk Insert (Batch) nativa do PostgreSQL.
    Caso a palavra já exista na tabela (conflito de restrição UNIQUE na coluna 'word'),
    a operação é ignorada silenciosamente (ON CONFLICT DO NOTHING), garantindo idempotência.

    Args:
        db (Session): Sessão ativa do SQLAlchemy (o commit deve ser gerido externamente).
        words_list (list[str]): Lista de palavras a serem adicionadas como stopwords.
    """
    if not words_list:
        return None

    clean_words = [{"word": w.strip().lower()} for w in words_list if w.strip()]

    if not clean_words:
        return None

    stmt = insert(DomainStopwordsModel).values(clean_words).on_conflict_do_nothing()

    db.execute(stmt)


def get_stopwords(db: Session) -> set[str]:
    """
    Recupera todas as stopwords de domínio cadastradas no banco de dados.

    Retorna um conjunto (Set) de stopwords

    Args:
        db (Session): Sessão ativa do SQLAlchemy.

    Returns:
        set[str]: Conjunto contendo todas as stopwords em letras minúsculas.
    """
    stmt = select(DomainStopwordsModel.word)
    resultados = db.scalars(stmt).all()
    return set(resultados)

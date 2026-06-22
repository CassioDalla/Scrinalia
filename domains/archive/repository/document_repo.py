import re

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveReviewStatus,
)
from domains.archive.schemas.schemas import ArchiveDocumentDTO


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


from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import get_db
from core.logger import logger
from domains.archive.models import ArchiveReviewStatus
from domains.archive.repository import DocumentRepository, TagRepository
from domains.archive.schemas.document_schema import ArchiveDocumentDTO
from domains.archive.services.tag_service import TagService
from domains.staging.models import StagingDocument

# Tamanho do lote para o Batch Commit
BATCH_SIZE = 500


def execute(db_session: Session) -> None:
    """
    Orquestrador responsável por copiar os dados estruturados da camada Staging
    e inicializar os registros na tabela fato da camada Archive.
    """
    logger.info("🚀 Iniciando migração do Staging para Archive")

    # Instancia o dos Repos e Serviço
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    tag_service = TagService(tag_repo, doc_repo)

    # yield_per(BATCH_SIZE) evita estourar a memória RAM ao buscar milhares de registros
    query = select(StagingDocument)
    documents_staging = db_session.scalars(query).yield_per(BATCH_SIZE)

    sucess = 0
    failures = 0

    # BUFFER DE OTIMIZAÇÃO: Acumula os vínculos N:N para inserir todos de uma vez
    batch_links = []

    for doc_staging in documents_staging:
        try:
            # 1. Monta o DTO com os metadados brutos (sem IA ainda)
            doc_dto = ArchiveDocumentDTO(
                description_id=doc_staging.description_id,
                original_title=doc_staging.title,
                document_date=doc_staging.document_date,
                summary=doc_staging.scope_content,
                staging_content_hash=doc_staging.raw_content_hash,
                original_thumbnail_url=doc_staging.thumb_down_link,
                storage_thumbnail_uri=None,
                reference_code=doc_staging.reference_code,
                level=doc_staging.level,
                producers=doc_staging.producers,
                admin_bio_history=doc_staging.admin_bio_history,
                admin_archival_history=doc_staging.admin_archival_history,
                provenance=doc_staging.provenance,
                scope_content=doc_staging.scope_content,
                language_name=doc_staging.language_name,
                archivist_notes=doc_staging.archivist_notes,
                final_title=None,
                semantic_search_vector=None,
                anomaly_reasons=None,
                review_status=ArchiveReviewStatus.PENDING_AI,
                execution_log={},
            )

            # 2. Persiste na tabela Fato (ArchiveDocuments)
            with db_session.begin_nested():
                was_saved = doc_repo.upsert_archive_document(doc_dto)

            if was_saved:
                # 3. Extrai e higieniza as tags antigas via Serviço de Domínio
                tags_dtos = tag_service.extract_and_clean_tags(doc_staging.indexing_points)
                tag_ids = tag_service.process_worker_tags(tags_dtos)

                if tag_ids:
                    batch_links.extend([{"description_id": doc_dto.description_id, "tag_id": t_id} for t_id in tag_ids])

                sucess += 1

                if sucess > 0 and sucess % BATCH_SIZE == 0:
                    if batch_links:
                        tag_repo.bulk_link_tags(batch_links)
                        batch_links.clear()

                    db_session.commit()
                    logger.info(f"⏳ Progresso: {sucess} documentos transferidos para a Archive...")

        except Exception as e:
            logger.error(f"❌ Erro ao transferir o documento {doc_staging.description_id}: {e}")
            failures += 1
            continue

    try:
        if batch_links:
            tag_repo.bulk_link_tags(batch_links)
        db_session.commit()
        logger.success(f"✅ Transferência concluída! Sucessos: {sucess} | Falhas: {failures}")
    except Exception as e:
        db_session.rollback()
        logger.critical(f"🔥 Erro crítico no commit final da transferência: {e}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db)

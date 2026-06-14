import re

from sqlalchemy import select

from core.crud import gold_crud
from core.database import get_db
from core.logger import logger
from core.models.gold_layer import GoldReviewStatus
from domains.staging.models import StagingDocument
from core.schemas.gold_schema import GoldDescriptionDTO, GoldTagDTO


# TODO mover isso para a tag_service
def extract_tags(indexing_points: str | None, stopwords_list: set[str] | None) -> list[GoldTagDTO]:
    """
    Aplica a limpeza aos Pontos de Acesso criados pelos arquivistas.
    """
    if not indexing_points:
        return []

    # Usa um set vazio se não passarem a lista
    stopwords = stopwords_list or set()

    tags_brutas = indexing_points.split(",")
    tags_limpas = set()

    for tag in tags_brutas:
        tag = tag.strip().lower()

        # Remove as stopwords exatas enviadas por parâmetro
        for junk in stopwords:
            tag = re.sub(rf"\b{junk}\b", "", tag).strip()

        tag = re.sub(r"\s+", " ", tag)

        if 2 < len(tag) <= 100:
            tags_limpas.add(tag)
        elif len(tag) > 100:
            logger.warning(f"⚠️ Tag ignorada por ser muito longa: '{tag[:50]}...'")

    # Transforma o Set de strings limpas numa lista de DTOs
    dto_list = []
    for tag_name in tags_limpas:
        dto_list.append(
            GoldTagDTO(
                name=tag_name,
                macro_category=None,
                ai_confidence_score=None,
            )
        )

    return dto_list


def executar_migracao_silver_gold():
    """
    Orquestrador que puxa os dados da Silver e inicializa a Ouro.
    """
    logger.info("🚀 Iniciando migração da base Silver para a Gold...")

    with get_db() as db:
        query = select(SilverDescriptionModel)
        documentos_silver = db.scalars(query).yield_per(500)

        sucess = 0

        for doc_silver in documentos_silver:
            try:
                doc_dto = GoldDescriptionDTO(
                    description_id=doc_silver.description_id,
                    original_title=doc_silver.title,
                    document_date=doc_silver.document_date,
                    summary=doc_silver.scope_content,
                    silver_content_hash=doc_silver.bronze_content_hash,
                    original_thumbnail_url=doc_silver.thumb_down_link,
                    storage_thumbnail_uri=None,
                    reference_code=doc_silver.reference_code,
                    level=doc_silver.level,
                    producers=doc_silver.producers,
                    admin_bio_history=doc_silver.admin_bio_history,
                    admin_archival_history=doc_silver.admin_archival_history,
                    provenance=doc_silver.provenance,
                    scope_content=doc_silver.scope_content,
                    language_name=doc_silver.language_name,
                    archivist_notes=doc_silver.archivist_notes,
                    final_title=None,
                    semantic_search_vector=None,
                    anomaly_reasons=None,
                    review_status=GoldReviewStatus.PENDING_AI,
                    execution_log={"migracao_base": "completed"},
                )

                stopword_list = gold_crud.get_stopwords(db)
                tags_dtos = extract_tags(doc_silver.indexing_points, stopword_list)

                was_saved = gold_crud.upsert_gold_description(db, doc_dto)

                if was_saved:
                    tag_ids = gold_crud.get_or_create_tags(db, tags_dtos)
                    gold_crud.link_description_relationships(
                        db,
                        description_id=doc_dto.description_id,
                        entity_ids=[],  # Lista vazia, pois as entidades são trabalho do Worker spaCy
                        tag_ids=tag_ids,
                    )
                    sucess += 1

                    if sucess % 100 == 0:
                        logger.info(f"⏳ Progresso: {sucess} documentos migrados para a Gold...")

            except Exception as e:
                logger.error(f"❌ Erro ao processar o documento {doc_silver.description_id}: {e}")
                # Faz o rollback da transação atual para não corromper o lote
                db.rollback()
                continue

        # O COMMIT ACONTECE NO FINAL, CONTROLADO PELO WORKER
        db.commit()
        logger.info(f"✅ Migração concluída! {sucess} documentos processados e carregados na Gold.")


if __name__ == "__main__":
    executar_migracao_silver_gold()

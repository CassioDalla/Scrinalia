from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import get_db
from core.logger import logger
from domains.archive.engines.LLMs.registry import EngineName, PresetName, get_engine
from domains.archive.models import ArchiveReviewStatus
from domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from domains.archive.repository import EntityRepository


def execute(
    db: Session,
    threshold_similaridade: float = 0.90,
    auto_resolve_threshold: float = 0.85,
    engine_name: EngineName = "ollama_judge",
    preset: PresetName = "gemma_4b_local",
) -> None:
    """
    Worker que atua como Juiz (Human-in-the-Loop) para resolver colisões semânticas.
    Usa um LLM estruturado para definir se um termo ambíguo deve pertencer
    à taxonomia de Assuntos (Tags) ou Entidades Nomeadas (NER).
    """
    logger.info(f"⚖️ Iniciando Worker Tag/Entity (Motor: {engine_name} | Preset: {preset})")

    # 1. Instancia o repositório e a Engine de IA usando o Registry
    ent_repo = EntityRepository(db)

    try:
        llm_engine = get_engine(engine_name=engine_name, preset=preset)
    except Exception as e:
        logger.critical(f"❌ Falha ao carregar o motor de julgamento: {e}")
        return

    # 2. Varredura Trigamática: Busca as colisões no acervo (PostgreSQL)
    logger.info("Iniciando Verredura de conflitos")
    conflitos_brutos = ent_repo.get_cross_domain_conflicts(threshold_similaridade)

    if not conflitos_brutos:
        logger.info("✨ Varredura concluída. Nenhum conflito semântico pendente encontrado.")
        return

    logger.info(f"✨ Varredura concluída. Encontrados: {len(conflitos_brutos)} conflitos")

    sucessos_auto = 0
    enviados_revisao = 0
    falhas = 0

    for row in conflitos_brutos:
        # Assinatura digital única para identificar este conflito no JSONB da fila
        payload_identificador = {"tag_id": row.tag_id, "entity_id": row.entity_id}

        # 3. Proteção contra Retrabalho: Verifica se este par já está na fila
        ja_processado = db.scalar(
            select(ArchiveAIReviewQueue.id).where(
                ArchiveAIReviewQueue.anomaly_type == AnomalyType.CROSS_DOMAIN_COLLISION,
                ArchiveAIReviewQueue.context_payload.contains(payload_identificador),
            )
        )

        if ja_processado:
            continue

        logger.info(
            f"🧠 Consultando IA para a ambiguidade: '{row.tag_name}' (Tag) vs '{row.entity_name}' ({row.entity_type})..."
        )

        try:
            # 4. Dispara a IA (Garante retorno estruturado via Pydantic/JSON)
            decisao = llm_engine.decide_conflict(
                tag_name=row.tag_name, entity_name=row.entity_name, entity_type=row.entity_type
            )

            status_final = ArchiveReviewStatus.NEEDS_REVIEW

            # 5. Ação Direta (Confiança Alta): O Repositório resolve a colisão de forma atómica
            if decisao.confidence >= auto_resolve_threshold:
                # Usamos um savepoint para proteger a iteração atual contra falhas estruturais (ex: Constraints)
                try:
                    with db.begin_nested():
                        ent_repo.resolve_cross_domain_conflict(
                            winner=decisao.winner, tag_id=row.tag_id, entity_id=row.entity_id
                        )

                    status_final = ArchiveReviewStatus.AI_APPROVED
                    sucessos_auto += 1
                    logger.success(f"✅ Auto-Resolvido como {decisao.winner} (Confiança: {decisao.confidence:.2f})")

                except Exception as e_bd:
                    logger.error(f"❌ Erro de banco de dados ao tentar auto-resolver '{row.tag_name}': {e_bd}")
                    falhas += 1
                    status_final = ArchiveReviewStatus.NEEDS_REVIEW  # Força a ida para a revisão humana
                    decisao.reason = f"FALHA NO BANCO: {e_bd} | " + decisao.reason
            else:
                enviados_revisao += 1
                logger.warning(f"⚠️ Dúvida! Confiança: {decisao.confidence:.2f} | Motivo: {decisao.reason}")

            # 6. Gravação do Log na Fila Genérica (Para a UI do Streamlit ler depois)
            novo_log = ArchiveAIReviewQueue(
                anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
                status=status_final,
                context_payload={
                    "tag_id": row.tag_id,
                    "tag_name": row.tag_name,
                    "entity_id": row.entity_id,
                    "entity_name": row.entity_name,
                    "entity_type": row.entity_type,
                },
                llm_decision=decisao.winner,
                llm_confidence=decisao.confidence,
                llm_reason=decisao.reason,
            )

            db.add(novo_log)
            # Commit iterativo: Se o script for interrompido a meio (Timeout/OOM),
            # não perdemos as dezenas de avaliações que a IA já processou.
            db.commit()

        except Exception as e:
            logger.error(f"❌ Erro grave ao processar o conflito '{row.tag_name}': {e}")
            db.rollback()
            falhas += 1
            continue

    logger.info(f"🏁 Juiz IA finalizado. Total processado: {sucessos_auto + enviados_revisao + falhas}")
    logger.info(
        f"📊 Auto-resolvidos (Expurgados): {sucessos_auto} | Fila Humana: {enviados_revisao} | Falhas técnicas: {falhas}"
    )


if __name__ == "__main__":
    with get_db() as db_session:
        execute(db_session)

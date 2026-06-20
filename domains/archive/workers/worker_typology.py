from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.logger import logger
from domains.archive import repository
from domains.archive.engines.base import TypologyEngine
from domains.archive.engines.classification.registry import EngineName, PresetName, get_engine
from domains.archive.models import ArchiveDocument


def execute(
    db: Session,
    engine_name: EngineName = "deberta_typology",
    preset: PresetName = "cpu_local",
    db_batch_size: int = 64,
    columns_to_classify: list[str] | None = None,
    **engine_kwargs,
) -> None:
    """
    Orquestrador do pipeline de Classificação de Tipologia Documental.

    Busca de forma contínua e em lotes os documentos no banco de dados que ainda
    não foram processados por esta rotina (verificando o campo JSON `execution_log`).
    Concatena dinamicamente as colunas solicitadas para formar o contexto e utiliza
    um motor de Inteligência Artificial injetado via Registry para classificar
    o documento em uma das tipologias ativas no sistema.

    Se a confiança da inferência (confidence score) for superior a 40%, vincula a
    `typology_id` ao documento. Independentemente do sucesso da classificação,
    o documento é carimbado como "DONE" para não entrar em loop. O processamento
    é blindado com proteção de memória (expunge_all) a cada transação concluída.

    Args:
        db (Session): Sessão do banco de dados.
        engine_name (EngineName, optional): Identificador do motor de IA registrado no
            sistema (ex: "deberta_typology"). Padrão é "deberta_typology".
        preset (PresetName, optional): Nome de uma pré-configuração (ex: "cpu_local", "gpu_cloud")
            que define os hiperparâmetros padrão do motor. Padrão é "cpu_local".
        db_batch_size (int, optional): Quantidade de documentos trazidos do banco
            e salvos por transação (commit). Padrão é 64.
        columns_to_classify (list[str] | None, optional): Lista com o nome exato das colunas
            do modelo `ArchiveDocument` que formarão o texto lido pela IA. Se `None`,
            utiliza internamente `["original_title"]`.
        **engine_kwargs: Argumentos arbitrários que serão repassados diretamente para
            o construtor do motor de IA, sobrescrevendo as configurações do `preset`
            (ex: `device="cuda:0"`, `max_length=256`).

    Raises:
        Exception: Se houver falha catastrófica ao instanciar o motor de processamento
            (ex: modelo não encontrado, falta de memória na máquina).

    Returns:
        None. O processo roda até a fila do banco de dados ser esvaziada.
    """

    logger.info(f"🚀 Iniciando Worker Classificador de Tipologias (Motor: {engine_name} | Preset: {preset})")

    columns_to_classify = columns_to_classify or ["original_title"]

    try:
        logger.info("Carregando Motor de Processamento...")
        engine: TypologyEngine = get_engine(engine_name=engine_name, preset=preset, **engine_kwargs)
    except Exception as e:
        logger.error(f"❌ Erro ao carregar o modelo: {e}")
        raise

    typologies_map = repository.get_active_typologies(db)
    print(typologies_map)
    if not typologies_map:
        logger.warning("⚠️ Nenhuma tipologia cadastrada no banco. Abortando Classificação.")
        return

    candidate_labels = list(typologies_map.keys())
    logger.info(f"📂 {len(candidate_labels)} tipologias carregadas.")

    # Pega os atributos da classe ArchiveDocument em tempo de execução
    filters_columns = [getattr(ArchiveDocument, col).is_not(None) for col in columns_to_classify]
    where_cond = [
        ArchiveDocument.typology_id.is_(None),
        or_(*filters_columns),
        or_(
            ArchiveDocument.execution_log.is_(None),
            ~ArchiveDocument.execution_log.has_key("worker_typology_classifier_v1"),
        ),
    ]

    query_count = select(func.count()).select_from(ArchiveDocument).where(*where_cond)
    total_documentos = db.scalar(query_count)

    if not total_documentos:
        logger.info("✨ Nenhum documento pendente encontrado. Finalizando.")
        return

    logger.info(f"🔍 Encontrados {total_documentos} documentos para classificar.")

    processados_total = 0

    while True:
        try:
            query = select(ArchiveDocument).where(*where_cond).limit(db_batch_size)

            lote_docs = db.scalars(query).all()

            if not lote_docs:
                break

            textos_buffer = []
            docs_validos = []

            # Preparação dos textos
            for doc in lote_docs:
                text_parts = []

                for col in columns_to_classify:
                    value = getattr(doc, col, None)
                    if value and str(value).strip():
                        text_parts.append(str(value).strip())

                text_to_classify = ". ".join(text_parts)

                if not text_to_classify:
                    log_atual = dict(doc.execution_log) if doc.execution_log else {}
                    log_atual["worker_typology_classifier_v1"] = "DONE"
                    doc.execution_log = log_atual
                    flag_modified(doc, "execution_log")

                    continue

                docs_validos.append(doc)
                textos_buffer.append(text_to_classify)

            if textos_buffer:
                logger.info(f"🧠 Processando lote de {len(textos_buffer)} documentos na IA...")

                try:
                    results = engine.classify(textos_buffer, candidate_labels, batch_size=1)
                except Exception as e:
                    logger.error(f"❌ Erro durante a inferência do pipeline: {e}")
                    db.rollback()
                    break

                # Aplicação dos resultados
                for doc, result in zip(docs_validos, results):  # noqa: B905
                    status_carimbo = "DONE"
                    try:
                        best_label = result["labels"][0]
                        confidence_score = result["scores"][0]

                        if confidence_score > 0.40:
                            t_id = typologies_map.get(best_label)

                            if t_id is not None:
                                doc.typology_id = t_id
                                logger.debug(
                                    f"Doc {doc.description_id} ➡️ {best_label} ({(confidence_score * 100):.1f}%)"
                                )
                            else:
                                logger.warning(
                                    f"Doc {doc.description_id}: Tipologia '{best_label}' não encontrada no mapa do banco."
                                )
                        else:
                            logger.debug(f"Doc {doc.description_id} ignorado (Baixa confiança)")

                        processados_total += 1

                    except Exception as e:
                        logger.error(f"❌ Erro ao atualizar documento {doc.description_id}: {e}")
                        status_carimbo = "ERROR"
                    try:
                        log_atual = dict(doc.execution_log) if doc.execution_log else {}
                        log_atual["worker_typology_classifier_v1"] = status_carimbo
                        doc.execution_log = log_atual
                        flag_modified(doc, "execution_log")
                    except Exception as e:
                        logger.critical(f"Falha crítica ao tentar carimbar erro no doc {doc.description_id}: {e}")

            try:
                db.commit()
                logger.info(f"⏳ Progresso parcial: {processados_total} documentos processados...")
            except Exception as e:
                db.rollback()
                logger.error(f"💥 Falha ao realizar commit no banco: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Erro inesperado no processamento do lote: {e}")
            db.rollback()
            break

    logger.success(f"✅ Worker Tipologia finalizado! Total processado nesta rodada: {processados_total}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db)

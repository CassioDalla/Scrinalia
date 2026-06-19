import re
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.logger import logger
from domains.archive import repository
from domains.archive.engines.base import EntityExtractionEngine
from domains.archive.engines.NER.registry import EngineName as ExtractEngineName
from domains.archive.engines.NER.registry import PresetName, get_engine
from domains.archive.models import ArchiveDocument


def _clean_raw_text(text: str) -> str:
    """Helper para limpar ruídos básicos antes de enviar para a IA."""

    if not text:
        return ""

    # 1. Remove URLs (http, https, www)
    text_no_urls = re.sub(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "", text)
    text_no_urls = re.sub(r"www\.\S+", "", text_no_urls)

    # 2. Remove e-mails
    text_no_urls = re.sub(r"[\w\.-]+@[\w\.-]+", "", text_no_urls)

    return text_no_urls.strip()


def execute(
    db: Session,
    engine_name: ExtractEngineName = "spacy_ner",
    preset: PresetName = "gpu",
    db_batch_size: int = 64,
    columns_to_extract: list[str] | None = None,
    **engine_kwargs: Any,
) -> None:
    """
    Orquestrador principal do pipeline de Extração de Entidades Nomeadas (NER).

    Implementa um padrão de processamento assíncrono em lotes (batch processing)
    com proteção de memória. O worker busca documentos no banco de dados que ainda
    não possuem a chave 'worker_ner_v1' no campo JSON `execution_log`.

    Para cada lote, o orquestrador:
    1. Concatena e higieniza as colunas textuais configuradas.
    2. Envia os textos para o motor de IA injetado (padrão Strategy via Registry)
       junto com regras institucionais carregadas dinamicamente.
    3. Persiste as entidades encontradas (UPSERT) e cria os relacionamentos N:N.
    4. Aplica um carimbo universal ("DONE" ou "ERROR") no documento para garantir
       que a fila avance, prevenindo loops infinitos em caso de falha de inferência.

    A sessão do banco é expurgada (expunge_all) a cada transação concluída para
    evitar vazamento de memória (Memory Leak) em execuções de longa duração.

    Args:
        db (Session): Sessão ativa do SQLAlchemy injetada pelo chamador.
        engine_name (ExtractEngineName, optional): Chave de registro do motor de
            processamento NLP a ser instanciado. Padrão é "spacy_ner".
        preset (PresetName, optional): Configuração predefinida de hardware/modelo
            para o motor (ex: "gpu", "cpu_local"). Padrão é "gpu".
        db_batch_size (int, optional): Limite de documentos puxados e commitados
            por transação no banco de dados. Padrão é 64.
        columns_to_extract (list[str] | None, optional): Lista de atributos da model
            `ArchiveDocument` que formarão o contexto analisado pela IA. Se `None`,
            utiliza `["original_title", "admin_bio_history", "provenance", "scope_content"]`.
        **engine_kwargs (Any): Argumentos nomeados extras repassados diretamente ao
            construtor do motor de IA para sobrescrever configurações do preset.

    Raises:
        Exception: Se houver uma falha crítica ao carregar o motor NLP ou as
            dependências de hardware configuradas.

    Returns:
        None. A esteira processa lotes continuamente até que a fila do banco de dados
        esteja completamente vazia.

    """
    logger.info(f"🚀 Iniciando Worker de NER (Motor: {engine_name} | Preset: {preset})")

    columns_to_extract = columns_to_extract or ["original_title", "admin_bio_history", "provenance", "scope_content"]

    try:
        logger.info("Carregando Motor de Extração e regras dinâmicas...")
        regras_dinamicas = repository.get_ner_synonyms_rules(db)
        # O motor deve ser capaz de receber essas regras no construtor ou via um método setup()
        engine: EntityExtractionEngine = get_engine(
            engine_name=engine_name, preset=preset, custom_rules=regras_dinamicas, **engine_kwargs
        )

    except Exception as e:
        logger.error(f"❌ Erro ao instanciar o motor NER: {e}")
        raise

    # 1. Filtros (Procuramos docs que AINDA NÃO têm o carimbo do NER)
    filters_columns = [getattr(ArchiveDocument, col).is_not(None) for col in columns_to_extract]
    where_cond = [
        or_(*filters_columns),
        or_(
            ArchiveDocument.execution_log.is_(None),
            ~ArchiveDocument.execution_log.has_key("worker_ner_v1"),
        ),
    ]

    # Pré-Query para os logs
    query_count = select(func.count()).select_from(ArchiveDocument).where(*where_cond)
    total_documents = db.scalar(query_count)

    if not total_documents:
        logger.info("✨ Nenhum documento pendente para extração de entidades.")
        return

    logger.info(f"🔍 Encontrados {total_documents} documentos para processar.")

    processed_docs_count = 0

    while True:
        try:
            query = select(ArchiveDocument).where(*where_cond).limit(db_batch_size)
            lote_docs = db.scalars(query).all()

            if not lote_docs:
                break

            texts_buffer = []
            docs_valid = []

            # 2. Preparação e Limpeza dos textos
            for doc in lote_docs:
                text_parts = []

                for col in columns_to_extract:
                    value = getattr(doc, col, None)
                    if value and str(value).strip():
                        text_parts.append(str(value).strip())

                text_contextualized = ". ".join(text_parts)
                text_contextualized = _clean_raw_text(text_contextualized)

                if not text_contextualized:
                    # Carimba docs vazios para não entrarem em loop
                    log_atual = dict(doc.execution_log) if doc.execution_log else {}
                    log_atual["worker_ner_v1"] = "DONE"
                    doc.execution_log = log_atual
                    flag_modified(doc, "execution_log")
                    continue

                docs_valid.append(doc)
                texts_buffer.append(text_contextualized)

            if texts_buffer:
                logger.info(f"🧠 Extraindo entidades de {len(texts_buffer)} documentos...")

                # 3. Inferência Batch isolada no try/except
                try:
                    # O motor deve receber uma lista de textos e retornar uma lista de resultados
                    # (onde cada resultado é uma lista de ArchiveEntityDTO)
                    ner_results = engine.extract(texts_buffer)
                except Exception as e:
                    logger.error(f"❌ Falha no processamento da IA: {e}")
                    db.rollback()
                    break

                # 4. Aplicação dos Resultados e Persistência no Banco
                for doc, dtos_entities in zip(docs_valid, ner_results, strict=True):
                    status_carimbo = "DONE"
                    doc = cast(ArchiveDocument, doc)
                    try:
                        # Se a IA encontrou entidades, processamos os vínculos
                        if dtos_entities:
                            entity_ids = repository.get_or_create_entities(db, dtos_entities)

                            repository.link_description_relationships(
                                db, description_id=doc.description_id, entity_ids=entity_ids, tag_ids=[]
                            )
                            logger.debug(f"Doc {doc.description_id} ➡️ {len(entity_ids)} entidades vinculadas.")
                        else:
                            logger.debug(f"Doc {doc.description_id} ➡️ Nenhuma entidade encontrada.")

                        processed_docs_count += 1

                    except Exception as e:
                        logger.error(f"❌ Erro estrutural ao salvar entidades do doc {doc.description_id}: {e}")
                        status_carimbo = "ERROR"

                    # 5. O Carimbo de Proteção Universal
                    try:
                        log_atual = dict(doc.execution_log) if doc.execution_log else {}
                        log_atual["worker_ner_v1"] = status_carimbo
                        doc.execution_log = log_atual
                        flag_modified(doc, "execution_log")
                    except Exception as e:
                        logger.critical(f"Falha crítica ao carimbar erro no doc {doc.description_id}: {e}")

            # 6. Commit de Lote e Limpeza de Memória
            try:
                db.commit()
                logger.info(f"⏳ Progresso parcial: {processed_docs_count} documentos enriquecidos...")
            except Exception as e:
                db.rollback()
                logger.error(f"💥 Falha ao realizar commit no banco: {e}")
                break

            db.expunge_all()

        except Exception as e:
            logger.error(f"❌ Erro inesperado no laço principal do Worker NER: {e}")
            db.rollback()
            break

    logger.success(f"✅ Worker NER finalizado! Total processado nesta rodada: {processed_docs_count}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db=db, db_batch_size=100)

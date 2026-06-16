import re
from typing import Literal, cast

import spacy
from spacy.language import Language
from spacy.pipeline import EntityRuler
from sqlalchemy import select

from core.database import get_db
from core.logger import logger
from domains.archive import repository
from domains.archive.models import ArchiveDocument
from domains.archive.schemas import ArchiveEntityDTO


def extract_entities_text(text: str, nlp_engine: Language) -> list[ArchiveEntityDTO]:
    """
    Executa o motor de Processamento de Linguagem Natural (spaCy) no texto alvo
    para extrair Entidades Nomeadas (PER, ORG, LOC).

    Aplica filtros de Qualidade de Dados (tamanho de string) e remove
    duplicidades exatas dentro do mesmo contexto de texto.

    Args:
        text (str): O texto concatenado do documento.
        nlp_engine (Language): O modelo do spaCy carregado em memória.

    Returns:
        list[ArchiveEntityDTO]: Lista de contratos de entidades validados.
    """
    if not text or not text.strip():
        return []

    doc = nlp_engine(text)
    entities_found = []
    labels = {"PER", "ORG", "LOC"}

    for ent in doc.ents:
        if ent.label_ in labels:
            # Se a regra do banco encontrou um ID canônico, use-o
            # Caso contrário, use o texto bruto normalizado.
            nome_limpo = ent.ent_id_ if ent.ent_id_ else ent.text.strip().title()

            # Barreira de Data Quality: Evita ruídos de caracteres soltos ou anomalias gigantes
            if 2 < len(nome_limpo) < 150:
                entity_type = cast(Literal["PER", "ORG", "LOC"], ent.label_)
                entities_found.append(ArchiveEntityDTO(name=nome_limpo, entity_type=entity_type))

    # Remove duplicadas idênticas no mesmo documento mantendo a ordem
    seen = set()
    unique_entities = []
    for ent in entities_found:
        key = (ent.name, ent.entity_type)
        if key not in seen:
            seen.add(key)
            unique_entities.append(ent)

    return unique_entities


def _clean_raw_text(text: str) -> str:
    if not text:
        return ""

    # 1. Remove URLs (http, https, www)
    text_no_urls = re.sub(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "", text)
    text_no_urls = re.sub(r"www\.\S+", "", text_no_urls)

    # 2. Remove e-mails
    text_no_urls = re.sub(r"[\w\.-]+@[\w\.-]+", "", text_no_urls)

    return text_no_urls.strip()


def execute_worker_ner() -> None:
    """
    Orquestrador principal do pipeline de Extração de Entidades (NER).

    Adota o padrão de Fila Descentralizada: busca no banco de dados documentos
    que ainda não possuem o carimbo 'ner_spacy_v1' no JSONB de log de execução,
    processa o texto, salva as entidades na dimensão e marca o documento como concluído.
    """
    logger.info("🚀 Iniciando Worker de NER (spaCy)...")

    try:
        logger.info("Carregando modelo spaCy (pt_core_news_lg)...")
        nlp = spacy.load("pt_core_news_lg")
    except OSError:
        logger.error(
            "❌ Modelo pt_core_news_lg não encontrado! "
            "Por favor, execute no terminal: python -m spacy download pt_core_news_lg"
        )
        raise

    with get_db() as db:
        ruler = cast(EntityRuler, nlp.add_pipe("entity_ruler", before="ner"))
        regras_dinamicas = repository.get_ner_synonyms_rules(db)
        if regras_dinamicas:
            ruler.add_patterns(regras_dinamicas)
            logger.info(f"{len(regras_dinamicas)} regras institucionais carregadas no motor NER.")

        # Busca documentos onde a chave do worker NER NÃO existe no execution_log
        query = select(ArchiveDocument).where(~ArchiveDocument.execution_log.has_key("ner_spacy_v1"))

        documentos_pendentes = db.scalars(query).yield_per(100)

        processados = 0
        for doc in documentos_pendentes:
            try:
                with db.begin_nested():
                    componentes_texto = [doc.original_title, doc.admin_bio_history, doc.provenance, doc.scope_content]
                    # Filtra apenas os campos preenchidos e junta-os com ponto e espaço
                    text_contextualized = ". ".join([txt.strip() for txt in componentes_texto if txt and txt.strip()])

                    text_contextualized = _clean_raw_text(text_contextualized)

                    # 1. Executa a extração NLP
                    dtos_entidades = extract_entities_text(text_contextualized, nlp)

                    # 2. Se houver entidades, salva na dimensão e recupera os IDs gerados
                    if dtos_entidades:
                        entity_ids = repository.get_or_create_entities(db, dtos_entidades)

                        # 3. Cria os vínculos na tabela associativa N:N (Mapeia Entidades, ignora Tags)
                        repository.link_description_relationships(
                            db, description_id=doc.description_id, entity_ids=entity_ids, tag_ids=[]
                        )

                    # 4.Mesmo se o spaCy não achar NENHUMA entidade,
                    # carimbamos o passaporte do documento como 'DONE' para tirá-lo da fila de pendências!
                    repository.stamp_ai_execution(db, doc.description_id, "ner_spacy_v1")
                    processados += 1

                    if processados % 50 == 0:
                        db.commit()
                        logger.info(f"⏳ Progresso: {processados} documentos enriquecidos pelo spaCy...")

            except Exception as e:
                logger.error(f"❌ Erro catastrófico no processamento do documento {doc.description_id}: {e}")
                continue

        db.commit()
        logger.success(f"✅ Worker NER finalizado com sucesso! Total de {processados} documentos processados.")


if __name__ == "__main__":
    execute_worker_ner()

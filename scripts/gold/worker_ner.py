from typing import Literal, cast

import spacy
from spacy.language import Language
from spacy.pipeline import EntityRuler
from sqlalchemy import select

from core.crud import gold_crud
from core.crud.gold_crud import load_nlp_rules
from core.database import get_db
from core.logger import logger
from core.models.gold_layer import GoldDescriptionModel
from core.schemas.gold_schema import GoldEntityDTO


def extract_entities_text(text: str, nlp_engine: Language) -> list[GoldEntityDTO]:
    """
    Roda o motor do spaCy no texto alvo e extrai as entidades permitidas (PER, ORG, LOC).
    Aplica filtros rigorosos de Data Quality e limpa duplicidades.
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
            if ent.ent_id_:
                nome_limpo = ent.ent_id_
            else:
                nome_limpo = ent.text.strip().title()

            # Barreira de Data Quality: Evita ruídos de caracteres soltos ou anomalias gigantes
            if 2 < len(nome_limpo) < 150:
                entity_type = cast(Literal["PER", "ORG", "LOC"], ent.label_)
                entities_found.append(GoldEntityDTO(name=nome_limpo, entity_type=entity_type))

    # Remove duplicadas idênticas no mesmo documento mantendo a ordem
    seen = set()
    unique_entities = []
    for ent in entities_found:
        key = (ent.name, ent.entity_type)
        if key not in seen:
            seen.add(key)
            unique_entities.append(ent)

    return unique_entities


def executar_worker_ner() -> None:
    """
    Orquestrador principal do pipeline de NER.
    Busca os checkpoints no JSONB e atualiza os metadados da Ouro de forma incremental.
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
        regras_dinamicas = load_nlp_rules(db)
        if regras_dinamicas:
            ruler.add_patterns(regras_dinamicas)
            logger.info(f"{len(regras_dinamicas)} regras institucionais carregadas no motor NER.")

        # Pega registros onde a migração terminou ('migracao_base' = 'completed')
        # E que o spaCy ainda NÃO processou ('ner_spacy' IS NULL)
        query = select(GoldDescriptionModel).where(
            (GoldDescriptionModel.execution_log["migracao_base"].astext == "completed")
            & (GoldDescriptionModel.execution_log["ner_spacy"].astext.is_(None))
        )

        documentos_pendentes = db.scalars(query).yield_per(100)

        processados = 0
        for doc in documentos_pendentes:
            try:
                componentes_texto = [doc.original_title, doc.admin_bio_history, doc.provenance, doc.scope_content]
                # Filtra apenas os campos preenchidos e junta-os com ponto e espaço
                text_contextualized = ". ".join([txt.strip() for txt in componentes_texto if txt and txt.strip()])

                # 1. Executa a extração NLP
                dtos_entidades = extract_entities_text(text_contextualized, nlp)

                # 2. Se houver entidades, salva na dimensão e recupera os IDs gerados
                if dtos_entidades:
                    entity_ids = gold_crud.get_or_create_entities(db, dtos_entidades)

                    # 3. Cria os vínculos na tabela associativa N:N (Mapeia Entidades, ignora Tags)
                    gold_crud.link_description_relationships(
                        db, description_id=doc.description_id, entity_ids=entity_ids, tag_ids=[]
                    )

                # 4.Mesmo se o spaCy não achar NENHUMA entidade,
                # carimbamos o passaporte do documento como 'completed' para tirá-lo da fila de pendências!
                gold_crud.stamp_ai_execution(db, doc.description_id, "ner_spacy")
                processados += 1

                if processados % 50 == 0:
                    db.commit()
                    logger.info(f"⏳ Progresso: {processados} documentos enriquecidos pelo spaCy...")

            except Exception as e:
                logger.error(f"❌ Erro catastrófico no processamento do documento {doc.description_id}: {e}")
                db.rollback()
                continue

        db.commit()
        logger.success(f"✅ Worker NER finalizado com sucesso! Total de {processados} documentos processados.")


if __name__ == "__main__":
    executar_worker_ner()

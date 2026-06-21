from core.logger import logger
from domains.archive.engines.clustering.registry import EngineName, PresetName, get_engine
from domains.archive.exceptions import EngineExecutionError, InvalidParam
from domains.archive.schemas.tag_schema import MacroCategoriesSuggestionResponse, MacroCategorySuggested


def run_suggestion_engine(
    texts_to_analize: list[str],
    engine_name: EngineName = "bertopic",
    preset: PresetName = "exploratorio_macro",
    **engine_kwargs,
) -> MacroCategoriesSuggestionResponse:

    if not texts_to_analize:
        raise InvalidParam("O parâmetro 'texts_to_analize' não foi passado.")

    logger.info(f"Carregando motor: {engine_name}, preset: ({preset})...")

    try:
        engine = get_engine(engine_name, preset=preset, **engine_kwargs)
        topics, topic_info_df = engine.discover_topics(list(texts_to_analize))

        found_categories: list[MacroCategorySuggested] = []

        # Formatação de Negócios
        for _, row in topic_info_df.iterrows():
            topic_id = row["Topic"]

            if topic_id == -1:
                continue

            # Cruza os IDs gerados com a lista de palavras enviadas para extrair amostras
            amostras = [texts_to_analize[i] for i, t in enumerate(topics) if t == topic_id]

            category_dto = MacroCategorySuggested(
                topic_id=topic_id,
                suggested_name=" - ".join(row["Representation"][:3]).title(),
                estimate_count=row["Count"],
                real_samples=amostras[:10],
            )

            found_categories.append(category_dto)
        logger.info(f"🎯 Foram sugeridas {len(found_categories)} Macro Categorias potenciais.")
        return MacroCategoriesSuggestionResponse(total_suggestions=len(found_categories), categories=found_categories)
    except Exception as e:
        logger.error("Falha na execução do motor de sugestão de categorias.")
        logger.error(e)
        raise EngineExecutionError(f"O motor '{engine_name}' falhou ao processar os textos.") from e

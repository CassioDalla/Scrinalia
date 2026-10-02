from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.engines.clustering.registry import EngineName, PresetName, get_engine
from memoria_curitibana.domains.archive.exceptions import EngineExecutionError, InvalidParam
from memoria_curitibana.domains.archive.schemas.tag_schema import (
    MacroCategoriesSuggestionResponse,
    MacroCategorySuggested,
)


def run_suggestion_engine(
    texts_to_analyze: list[str],
    engine_name: EngineName = "bertopic",
    preset: PresetName = "exploratory_macro",
    **engine_kwargs,
) -> MacroCategoriesSuggestionResponse:

    if not texts_to_analyze:
        raise InvalidParam("O parâmetro 'texts_to_analyze' não foi passado.")

    logger.info(f"Loading engine: {engine_name}, preset: ({preset})...")

    try:
        engine = get_engine(engine_name, preset=preset, **engine_kwargs)
        topics, topic_info_df = engine.discover_topics(list(texts_to_analyze))

        found_categories: list[MacroCategorySuggested] = []

        # Business Formatting
        for _, row in topic_info_df.iterrows():
            topic_id = int(row["Topic"])

            if topic_id == -1:
                continue

            # Cross-references the generated IDs with the list of words sent to extract samples
            samples = [texts_to_analyze[i] for i, t in enumerate(topics) if t == topic_id]

            category_dto = MacroCategorySuggested(
                topic_id=topic_id,
                suggested_name=" - ".join(row["Representation"][:3]).title(),
                estimate_count=int(row["Count"]),
                real_samples=samples[:10],
            )

            found_categories.append(category_dto)
        logger.info(f"🎯 {len(found_categories)} potential Macro Categories were suggested.")
        return MacroCategoriesSuggestionResponse(total_suggestions=len(found_categories), categories=found_categories)
    except Exception as e:
        logger.error("Failure executing the category suggestion engine.")
        logger.error(e)
        raise EngineExecutionError(f"O motor '{engine_name}' falhou ao processar os textos.") from e

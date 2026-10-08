from typing import Any

from pandas import DataFrame

from scrinalia.core.logger import logger
from scrinalia.domains.archive.engines.clustering.registry import (
    PRESETS,
    EngineName,
    PresetName,
    get_engine,
)
from scrinalia.domains.archive.exceptions import EngineExecutionError, InvalidParam
from scrinalia.domains.archive.schemas.tag_schema import (
    MacroCategoriesSuggestionResponse,
    MacroCategorySuggested,
)

# Below this the embedding + UMAP + HDBSCAN stack cannot form meaningful clusters.
# The API answers with an empty suggestion instead of asking the engine to fail.
MIN_TEXTS_TO_CLUSTER = 5

# Texts per topic used to scale ``min_topic_size`` with the corpus. The fixed values
# baked into the presets (15 for macro) assume a large collection; with a real
# collection of ~40 tags that guarantee produced zero clusters and a 422.
_TEXTS_PER_TOPIC = 10

_FALLBACK_PRESET: PresetName = "exploratory_fine"


def resolve_min_topic_size(preset: PresetName, corpus_size: int) -> int:
    """
    Scales the minimum cluster size with the corpus, capped by the preset's intent.

    A preset keeps its ceiling (``exploratory_macro`` still aims at generic drawers),
    but the floor is relaxed when there are few texts. With 39 tags the macro preset
    drops from 15 to 3, which is the configuration verified to produce coherent
    clusters ("Urbano - Pavimentação - Via", "Epidemia - Dengue - Saúde").
    """
    base = int(PRESETS.get(preset, {}).get("min_topic_size", _TEXTS_PER_TOPIC))
    return max(2, min(base, corpus_size // _TEXTS_PER_TOPIC))


def _format_suggestions(
    texts_to_analyze: list[str], topics: list[int], topic_info_df: DataFrame
) -> list[MacroCategorySuggested]:
    """Translates the raw BERTopic output into the business DTO, dropping the noise topic."""
    found_categories: list[MacroCategorySuggested] = []

    for _, row in topic_info_df.iterrows():
        topic_id = int(row["Topic"])

        if topic_id == -1:
            continue

        # Cross-references the generated IDs with the list of words sent to extract samples
        samples = [texts_to_analyze[i] for i, t in enumerate(topics) if t == topic_id]

        found_categories.append(
            MacroCategorySuggested(
                topic_id=topic_id,
                suggested_name=" - ".join(row["Representation"][:3]).title(),
                estimate_count=int(row["Count"]),
                real_samples=samples[:10],
            )
        )

    return found_categories


def _build_engine_kwargs(preset: PresetName, corpus_size: int, engine_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Lets an explicit caller override win over the adaptive default."""
    kwargs = dict(engine_kwargs)
    kwargs.setdefault("min_topic_size", resolve_min_topic_size(preset, corpus_size))
    return kwargs


def run_suggestion_engine(
    texts_to_analyze: list[str],
    engine_name: EngineName = "bertopic",
    preset: PresetName = "exploratory_macro",
    **engine_kwargs,
) -> MacroCategoriesSuggestionResponse:
    """
    Discovers macro-category candidates from a corpus of texts.

    The preset is treated as an intent, not a hard configuration: ``min_topic_size`` is
    scaled to the corpus and, when the chosen preset still cannot form a cluster, the
    routine retries once with ``exploratory_fine``. A corpus that produces no cluster at
    all is reported as an empty suggestion with a message, never as an engine error —
    only a bad engine/preset name raises ``EngineExecutionError``.
    """
    if not texts_to_analyze:
        raise InvalidParam("O parâmetro 'texts_to_analyze' não foi passado.")

    corpus_size = len(texts_to_analyze)

    candidate_presets: list[PresetName] = [preset]
    if preset != _FALLBACK_PRESET:
        candidate_presets.append(_FALLBACK_PRESET)

    for attempt_preset in candidate_presets:
        logger.info(f"Loading engine: {engine_name}, preset: ({attempt_preset})...")

        try:
            engine = get_engine(
                engine_name,
                preset=attempt_preset,
                **_build_engine_kwargs(attempt_preset, corpus_size, engine_kwargs),
            )
        except ValueError as e:
            # Unknown engine/preset is a configuration mistake: surface it, do not
            # disguise it as "not enough data".
            logger.error("Failure configuring the category suggestion engine.")
            logger.error(e)
            raise EngineExecutionError(f"O motor '{engine_name}' falhou ao processar os textos.") from e

        try:
            topics, topic_info_df = engine.discover_topics(list(texts_to_analyze))
        except Exception as e:
            logger.warning(f"⚠️ Preset '{attempt_preset}' could not cluster {corpus_size} texts: {e}")
            continue

        found_categories = _format_suggestions(texts_to_analyze, topics, topic_info_df)

        if found_categories:
            logger.info(f"🎯 {len(found_categories)} potential Macro Categories were suggested.")
            return MacroCategoriesSuggestionResponse(
                total_suggestions=len(found_categories), categories=found_categories
            )

    logger.warning(f"⚠️ No semantic cluster could be formed from the {corpus_size} available texts.")
    return MacroCategoriesSuggestionResponse(
        total_suggestions=0,
        categories=[],
        message="⚠️ Não foi possível formar clusters semânticos com o volume atual de textos.",
    )

from dataclasses import dataclass


@dataclass(frozen=True)
class TypologyRunnerConfig:
    """Business thresholds for the typology classification worker."""

    confidence_threshold: float = 0.40
    columns_to_classify: tuple[str, ...] = ("original_title",)


@dataclass(frozen=True)
class NerRunnerConfig:
    """Business defaults for the NER extraction worker."""

    columns_to_extract: tuple[str, ...] = ("original_title", "admin_bio_history", "provenance", "scope_content")


@dataclass(frozen=True)
class MacroCategoryRunnerConfig:
    """
    Business thresholds for the macro-category (subject axis) classification worker.

    Two thresholds, because they answer different questions and the measurement separated
    them:

    * ``confidence_threshold`` (0.55) — the floor to **link** a drawer. It is no longer 0.40:
      measured on the labelled set, a wrong answer carries 0.455 on average and a right one
      0.705, so 0.40 let most wrong answers through. At 0.55 the tool stops guessing.
    * ``review_threshold`` (0.55) — at or above the floor the tag is linked; below it the tag
      stays orphan **and enters the review queue**, so the curator sees a decision to make
      instead of a silent absence. An empty badge beats a wrong badge in a UI that is about to
      amplify both.
    """

    confidence_threshold: float = 0.55
    review_threshold: float = 0.55


@dataclass(frozen=True)
class IngestionRunnerConfig:
    """Retry and sliding-window policy for the ingestion worker."""

    max_retries: int = 3
    discovery_window_days: int = 30
    scraped_ttl_days: int = 1

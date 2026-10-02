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
class IngestionRunnerConfig:
    """Retry and sliding-window policy for the ingestion worker."""

    max_retries: int = 3
    discovery_window_days: int = 30
    scraped_ttl_days: int = 1

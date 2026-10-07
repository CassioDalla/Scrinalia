"""Typed application settings, loaded from the environment and the local ``.env``."""

from functools import lru_cache
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Single source of truth for configuration.

    Real environment variables win over the ``.env`` file, which is the same
    precedence the previous ``load_dotenv``/``os.getenv`` pair had. Every optional
    value keeps an explicit default, so importing the application never fails on a
    missing variable; values that *are* present get validated and coerced (an
    invalid ``DB_PORT`` fails fast instead of producing a broken DSN).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DB_USER: str = "admin"
    DB_PASS: SecretStr = SecretStr("admin123")
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "memoriacuritibana"

    # ArqDoc (source archival system)
    ARQDOC_BASE_URL: str | None = None
    ARQDOC_VIEW_ENDPOINT: str | None = None

    # Public Arquivo site
    PUBLIC_SCRAPE_URL: str | None = None
    PUBLIC_SCRAPE_DETAIL_URL: str | None = None

    # Object storage
    S3_ENDPOINT_URL: str | None = None
    S3_BUCKET_NAME: str | None = None
    S3_ACCESS_KEY: SecretStr | None = None
    S3_SECRET_KEY: SecretStr | None = None

    # LLM hosts
    OLLAMA_HOST_URL: str | None = None

    # Observability
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    #: How many worker runs the API's background executor accepts at once. One by default: the
    #: workers are CPU-bound and the pipeline has an order, so a second torch model on the same CPU
    #: slows the first without producing more.
    WORKER_RUNTIME_MAX_WORKERS: int = 1

    @property
    def DATABASE_URL(self) -> str:
        """DSN with user and password percent-encoded, so odd credentials cannot break the URL."""
        user = quote(self.DB_USER, safe="")
        password = quote(self.DB_PASS.get_secret_value(), safe="")
        return f"postgresql://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor; tests can isolate configuration with ``get_settings.cache_clear()``."""
    return Settings()


#: Host the Ollama-backed engines talk to when neither the caller nor the environment says
#: otherwise. The presets deliberately do **not** carry a host: it is environment configuration,
#: not part of a model's identity. Hardcoding it in ``PRESETS`` made ``OLLAMA_HOST_URL`` a lie for
#: every engine built through a preset — the variable only reached the generic ``OllamaClient``.
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def resolve_ollama_host(explicit: str | None = None) -> str:
    """Explicit host wins, then ``OLLAMA_HOST_URL``, then the local default."""
    return explicit or settings.OLLAMA_HOST_URL or DEFAULT_OLLAMA_HOST


settings = get_settings()

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

    # Public site that gets scraped. Read at the composition point and handed to the adapter,
    # never by the adapter itself: an adapter that reads global settings cannot be pointed at
    # another origin, which is what plural ingestion will need.
    PUBLIC_SCRAPE_URL: str | None = None
    PUBLIC_SCRAPE_DETAIL_URL: str | None = None

    # Which origin the staging transform reads. Names the ``SourceSchema`` in
    # ``domains/ingestion/sources.py`` — the site's field labels and where each one lands. It has
    # **no default on purpose**: a fallback would make an installation that never declared its
    # origin read the reference site's vocabulary, which is the defect ADR 0008 removed from the
    # collection catalogue. Required by the staging pipeline, not by boot.
    ACERVO_SOURCE: str | None = None

    # Language of the collection. Selects the profile in ``core/language`` that the date
    # parser, the term guard, the plural rules and the clustering/NER presets read. The
    # full-text dictionary is part of the profile and reaches a **generated column**: changing
    # this value is a schema change, and ``alembic check`` reports the drift until a migration
    # rebuilds ``search_vector``.
    ACERVO_LANGUAGE: str = "pt-BR"

    # Object storage
    S3_ENDPOINT_URL: str | None = None
    S3_BUCKET_NAME: str | None = None
    S3_ACCESS_KEY: SecretStr | None = None
    S3_SECRET_KEY: SecretStr | None = None

    # LLM hosts
    OLLAMA_HOST_URL: str | None = None

    # Authentication. The session cookie is **first-party**: ``asgi.py`` mounts the curator SPA at
    # ``/``, so the browser talks to the same origin and no token ever reaches JavaScript. See
    # ``docs/adr/0009-authentication-and-authorization.md``.
    AUTH_SESSION_COOKIE_NAME: str = "scrinalia_session"

    #: How long a session lives. Sliding: a request that finds the session older than
    #: ``AUTH_SESSION_TOUCH_MINUTES`` pushes the expiry forward, so an archivist working all day is
    #: not logged out mid-task while an abandoned session still dies.
    AUTH_SESSION_TTL_MINUTES: int = 720
    AUTH_SESSION_TOUCH_MINUTES: int = 15

    #: ``Secure`` on the session cookie. It must stay **false** for a plain-HTTP install on a LAN:
    #: the browser silently drops a ``Secure`` cookie over ``http://``, so the login looks like it
    #: worked while nothing is stored, and the next request is anonymous again. A deployment behind
    #: HTTPS sets this to true.
    AUTH_COOKIE_SECURE: bool = False

    #: Password policy, checked in the domain and not only in the request schema, because the CLI
    #: creates accounts without going through an HTTP body.
    AUTH_PASSWORD_MIN_LENGTH: int = 12

    #: argon2id cost, the parameters that live inside the hash string. The defaults are RFC 9106's
    #: second recommendation (64 MiB, t=3, p=4). They are settings for two reasons: a test suite can
    #: lower the memory cost instead of paying ~60 ms per login, and an institution can raise it
    #: without touching code. Raising them does **not** invalidate existing hashes — they keep
    #: verifying and are upgraded on the next successful login.
    AUTH_PASSWORD_MEMORY_KIB: int = 65536
    AUTH_PASSWORD_TIME_COST: int = 3
    AUTH_PASSWORD_PARALLELISM: int = 4

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

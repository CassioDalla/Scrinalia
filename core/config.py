import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Banco de Dados
    DB_USER = os.getenv("DB_USER", "admin")
    DB_PASS = os.getenv("DB_PASS", "admin123")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "memoriacuritibana")

    # URL de conexão
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    # Configurações do ArqDoc
    ARQDOC_BASE_URL = os.getenv("ARQDOC_BASE_URL")
    ARQDOC_VIEW_ENDPOINT = os.getenv("ARQDOC_VIEW_ENDPOINT")

    # Site público Arquivo
    PUBLIC_SCRAPE_URL = os.getenv("PUBLIC_SCRAPE_URL")
    PUBLIC_SCRAPE_DETAIL_URL = os.getenv("PUBLIC_SCRAPE_DETAIL_URL")

    # Storage
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")


    #LLM Hosts
    OLLAMA_HOST_URL = os.getenv("OLLAMA_HOST_URL")


settings = Settings()

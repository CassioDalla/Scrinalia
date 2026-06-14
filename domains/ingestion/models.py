import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base


class ScrapeStatus(enum.Enum):
    """
    Representa o estado atual de um documento na fila de extração.

    - PENDING: Na fila, aguardando processamento.
    - DONE: Extraído e salvo com sucesso na tabela RawData.
    - NETWORK_ERROR: Falha transitória (timeout, queda de conexão). Permite retentativas.
    - NOT_FOUND: Erro 404. O documento não existe mais no sistema de origem.
    - FATAL_ERROR: Erro definitivo (HTML malformado, limite de retentativas estourado).
    """

    PENDING = "PENDING"
    DONE = "DONE"
    NETWORK_ERROR = "NETWORK_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FATAL_ERROR = "FATAL_ERROR"


class ScrapingQueue(Base):
    """
    Tabela de controle (Fila) para o motor de ingestão de dados.

    Armazena os identificadores únicos encontrados no acervo legado e gerencia
    o estado de extração de cada um, aplicando conceitos de Sliding Window e
    controle de concorrência (retries).

    Attributes:
        description_id: O ID legado do documento (Chave de negócio).
        scrape_status: O estado atual do processamento deste ID.
        discovered_at: Data em que o ID foi encontrado pela primeira vez no acervo.
        last_scraped_at: Data da última tentativa (com sucesso ou falha) de extração.
        retry_count: Quantidade de falhas transitórias consecutivas.
        last_error_message: Log do último erro capturado para facilitar o debug.
    """

    __tablename__ = "scraping_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    description_id: Mapped[str] = mapped_column(String(60), unique=True)

    scrape_status: Mapped[ScrapeStatus] = mapped_column(
        Enum(ScrapeStatus, name="scrape_status_enum", create_type=False), default=ScrapeStatus.PENDING
    )

    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    last_error_message: Mapped[str | None] = mapped_column(Text)


class RawData(Base):
    """
    Repositório de dados brutos (equivalente à camada Bronze/Ingestion).

    Armazena o payload exato retornado pelos adaptadores,
    sem nenhum tratamento, tipagem ou limpeza, garantindo a preservação
    do dado original para futuras reestruturações na camada Silver (Staging).

    Attributes:
        description_id: O ID legado do documento, usado como chave de junção.
        content_hash: Hash criptográfico (ex: SHA-256) do payload para controle
            de idempotência e detecção de atualizações silenciosas na origem.
        raw_title: Título original sujo para buscas rápidas ou debug.
        payload: Dicionário completo com todos os metadados extraídos.
    """

    __tablename__ = "raw_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    description_id: Mapped[str] = mapped_column(String(60), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))

    raw_title: Mapped[str | None] = mapped_column(String(500))

    payload: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScrapeStatus(enum.Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    NETWORK_ERROR = "NETWORk_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FATAL_ERROR = "FATAL_ERROR"


class ScrapingQueue(Base):
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

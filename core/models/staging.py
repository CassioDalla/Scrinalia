from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StagingDescription(Base):
    __tablename__ = "staging_descriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    description_id: Mapped[str] = mapped_column(String(60), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))

    raw_title: Mapped[str | None] = mapped_column(String(500))

    payload: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

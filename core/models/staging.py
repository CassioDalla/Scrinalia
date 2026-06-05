import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class StagingStatus(enum.Enum):
    PENDING = "PENDING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    NETWORK_ERROR = "NETWORK_ERROR"
    FATAL_ERROR = "FATAL_ERROR"


class ValidationRules(Base):
    __tablename__ = "validation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="WARNING")


class StagingDescription(Base):
    __tablename__ = "staging_descriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    description_id: Mapped[str] = mapped_column(String(60), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))

    raw_title: Mapped[str | None] = mapped_column(String(500))
    suggested_title: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[StagingStatus] = mapped_column(
        Enum(StagingStatus, name="staging_status_enum", create_type=False), default=StagingStatus.PENDING
    )

    payload: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    flags: Mapped[list["StagingFlag"]] = relationship(back_populates="staging_doc")


class StagingFlag(Base):
    __tablename__ = "staging_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    staging_id: Mapped[int] = mapped_column(ForeignKey("staging_descriptions.id", ondelete="CASCADE"))
    rule_id: Mapped[int] = mapped_column(ForeignKey("validation_rules.id", ondelete="CASCADE"))
    error_context: Mapped[str | None] = mapped_column(String(255))

    staging_doc: Mapped["StagingDescription"] = relationship(back_populates="flags")

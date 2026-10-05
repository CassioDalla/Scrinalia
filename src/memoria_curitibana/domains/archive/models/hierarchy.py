from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from memoria_curitibana.core.base import Base

if TYPE_CHECKING:
    from .document import ArchiveDocument


class ArchiveDescriptionLevel(Base):
    """
    Catalogue of description levels (the NOBRADE/ISAD(G) ladder), owned by the archivist.

    The ladder is a table and not an enum because the norm is only the seed: NOBRADE runs from
    the *Acervo da entidade custodiadora* (0) down to the *Item documental* (5), but a curator
    may add or rename a rung without a deploy. ``code`` is the stable machine key the proposal
    and the API speak; ``name`` is the text the archivist (and the source) sees.

    ``name`` is deliberately seeded with **the spelling the source actually declares**
    (``"Item Documental"``, ``"Dossiê/Processo"``), not with the wording of the norm. The
    migration matches the ``level`` text of 3,608 real descriptions against it, and seeding
    ``"Item documental"`` would have failed every one of the 2,478 items on capitalisation
    alone. The norm's wording lives in ``description``; ``aliases`` is where the curator
    registers the spellings the normaliser must accept besides the canonical ``name``.

    ``requires_parent`` is the roadmap's ``is_required`` with the ambiguity removed: a node at
    this level may not be a root (a Dossiê only exists under something). It is **not** "every
    description must have this level". ``allows_children`` is the opposite end: an Item is a
    leaf, so giving it a child is a validation error, not a convention.
    """

    __tablename__ = "archive_description_levels"

    level_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: Position on the ladder. Not capped at 5: the seed has six rungs, but the catalogue is
    #: the archivist's, and a CHECK ceiling would turn "add a sub-level" into a migration.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Alternative spellings accepted by ``domain.level_catalog`` when matching source text.
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default="{}")

    requires_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    allows_children: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(back_populates="level_ref")

    __table_args__ = (CheckConstraint("ordinal >= 0", name="chk_description_level_ordinal"),)

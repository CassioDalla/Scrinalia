"""
The vocabulary of the collection: what the archive itself declares, as rows.

Two things were constants in the code and are properties of *this* collection, not of the
system: the map of arrangement tokens to the names the curator reads (``ED`` -> ``Edificações``,
``IPPUC`` -> the institute), and the gazetteer of toponyms and person names the subject guard
recognises. The first made the hierarchy proposal suggest Curitiba's secretariats to any
installation; the second refused 16 person names and 34 bairros that another archive would not
even have.

Both are tables now, following the three catalogues already in the system (levels, drawers,
typologies): the seed is the reference collection, the archivist extends it without a deploy, and
retiring a row is ``is_active=false`` — never a delete. A suggestion that disappeared would look
like a bug to the person who added it.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base

from .enums import CollectionTermKind


class ArchiveArrangementTerm(Base):
    """
    One arrangement token and the name the proposal suggests for the rung that carries it.

    ``token`` is either a single code token (``IPPUC``, ``ED``) or a full code (``BR PRADAP``),
    stored normalised: uppercase, single spaces. The proposal reads the full code first and falls
    back to its last token, so a row keyed by the whole code wins over a row keyed by its last
    token — which is what makes "the root has its own name" expressible next to "``SMU`` is the
    secretariat".

    Suggestions only. Nothing here creates a node: the archivist reviews the proposal and the
    materialisation writes the tree. A row that stops being wanted is deactivated, so the same
    question is not asked again with the same wrong answer.
    """

    __tablename__ = "archive_arrangement_vocabulary"

    term_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("token", name="uq_archive_arrangement_vocabulary_token"),)


class ArchiveCollectionTerm(Base):
    """
    A term the collection carries that is **not** a subject, with the axis it goes to instead.

    The subject guard is deterministic and stays so: ``is_subject_candidate`` is a pure function
    of the spelling. What changes is where two of its families come from. ``STREET``,
    ``PLACEHOLDER``, ``YEAR`` and ``MEASURE`` are properties of the language and live in the
    language profile; the toponyms and the person names are properties of the collection and live
    here, read once per run and handed to the guard.

    The kind separates the two destinations: a place claims the ``PLACE`` facet, a person name
    goes nowhere (it is the producer, the same reasoning that retired the ``Pessoa`` drawer).
    """

    __tablename__ = "archive_collection_terms"

    term_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Stored normalised (lowercase, trimmed): the guard matches on that form, and two spellings
    #: that differ only in case would otherwise be two rows the curator cannot tell apart.
    term: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    kind: Mapped[CollectionTermKind] = mapped_column(
        Enum(CollectionTermKind, name="collection_term_kind", create_type=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("term", "kind", name="uq_archive_collection_terms_term_kind"),)

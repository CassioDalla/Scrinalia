"""add the description level catalog

Revision ID: a1f2c3d4e5b6
Revises: cc60ffae1e5c
Create Date: 2026-10-04 21:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1f2c3d4e5b6"
down_revision: str | Sequence[str] | None = "cc60ffae1e5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The rungs the catalogue starts with.
#:
#: Duplicated from ``domain.level_catalog.NOBRADE_LEVELS`` on purpose, following the precedent
#: of ``f8760cab6d12``: a migration must keep describing the state it produces even if the
#: application constant is edited later, or replaying history stops reproducing it. A test pins
#: the two together.
#:
#: ``name`` is the spelling the **source declares** wherever the source declares one
#: (``"Item Documental"``, ``"Dossiê/Processo"``). Seeding the norm's wording
#: (``"Item documental"``) would have failed every one of the 2,478 items on capitalisation
#: alone when ``b2c3d4e5f6a7`` maps the free text into the foreign key. The NOBRADE wording
#: lives in ``description`` and, where useful, in ``aliases``.
LEVELS: tuple[tuple[int, str, str, str, tuple[str, ...], bool, bool], ...] = (
    (
        0,
        "acervo",
        "Acervo da entidade custodiadora",
        "Conjunto documental sob a guarda de uma mesma entidade custodiadora. É a raiz da árvore.",
        ("Acervo", "Acervo da entidade"),
        False,
        True,
    ),
    (
        1,
        "fundo",
        "Fundo",
        "Fundo ou coleção: o conjunto produzido por uma mesma instituição ou pessoa.",
        ("Fundo ou coleção", "Coleção", "Fundo ou colecao"),
        False,
        True,
    ),
    (
        2,
        "secao",
        "Seção",
        "Divisão administrativa ou funcional do fundo.",
        ("Secao", "Seccao"),
        False,
        True,
    ),
    (
        3,
        "serie",
        "Série",
        "Agrupamento de descrições por afinidade de função, atividade ou tipo documental.",
        ("Serie", "Subsérie", "Subserie"),
        False,
        True,
    ),
    (
        4,
        "dossie",
        "Dossiê/Processo",
        "Nível obrigatório da norma: o conjunto de documentos reunidos por um mesmo assunto ou processo.",
        ("Dossiê ou processo", "Dossiê", "Dossie", "Processo"),
        True,
        True,
    ),
    (
        5,
        "item",
        "Item Documental",
        "Unidade documental indivisível. Não admite filhos.",
        ("Item documental", "Item"),
        True,
        False,
    ),
)


def upgrade() -> None:
    """
    Creates the catalogue of description levels and seeds the NOBRADE ladder.

    The seed is idempotent (``ON CONFLICT (name)``): a database that already carries some of
    the rungs converges instead of failing. No ``level_id`` is written by hand anywhere, so the
    sequence stays the only source of ids and no ``setval`` is ever needed later.
    """
    op.create_table(
        "archive_description_levels",
        sa.Column("level_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("requires_parent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allows_children", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="chk_description_level_ordinal"),
        sa.PrimaryKeyConstraint("level_id"),
        sa.UniqueConstraint("ordinal", name="uq_description_level_ordinal"),
        sa.UniqueConstraint("code", name="uq_description_level_code"),
        sa.UniqueConstraint("name", name="uq_description_level_name"),
    )

    connection = op.get_bind()
    insert_level = sa.text(
        """
        INSERT INTO archive_description_levels
            (ordinal, code, name, description, aliases, requires_parent, allows_children, is_active)
        VALUES
            (:ordinal, :code, :name, :description, :aliases, :requires_parent, :allows_children, true)
        ON CONFLICT (name) DO UPDATE
            SET ordinal = EXCLUDED.ordinal,
                code = EXCLUDED.code,
                description = EXCLUDED.description,
                aliases = EXCLUDED.aliases,
                requires_parent = EXCLUDED.requires_parent,
                allows_children = EXCLUDED.allows_children
        """
    )
    for ordinal, code, name, description, aliases, requires_parent, allows_children in LEVELS:
        connection.execute(
            insert_level,
            {
                "ordinal": ordinal,
                "code": code,
                "name": name,
                "description": description,
                "aliases": list(aliases),
                "requires_parent": requires_parent,
                "allows_children": allows_children,
            },
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("archive_description_levels")

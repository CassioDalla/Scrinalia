"""replace the subject vocabulary and retire the non-subject drawers

Revision ID: f8760cab6d12
Revises: 16b3b222c85c
Create Date: 2026-10-04 19:42:17.947452

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8760cab6d12"
down_revision: str | Sequence[str] | None = "16b3b222c85c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The drawers the classifier reads. Duplicated from
#: ``domain.vocabulary.SUBJECT_CATEGORIES`` on purpose: a migration must keep describing the
#: state it produces even if the application constant is edited later, otherwise replaying
#: history stops reproducing it. A test pins the two together.
SUBJECT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Urbanismo e Arquitetura", "Construção, materiais, tipologia construtiva e desenho urbano."),
    ("Mobilidade e Transporte", "Circulação, ferrovia, veículos e transporte público."),
    ("Religião", "Edifícios, instituições e práticas religiosas."),
    ("Meio Ambiente e Áreas Verdes", "Parques, rios, vegetação e ecologia."),
    ("Economia e Comércio", "Comércio, serviços, indústria e abastecimento."),
    ("Educação e Cultura", "Escolas, museus, eventos, esporte e produção cultural."),
    ("Patrimônio e Preservação", "Tombamento e o patrimônio construído como política pública."),
    ("Assistência e Questões Sociais", "População, vulnerabilidade, trabalho e ação social."),
)

#: Drawers that leave the subject axis. Deactivated, never deleted: the FK is
#: ``ON DELETE SET NULL``, so deleting would orphan the tags silently while destroying the
#: record that the drawer existed. Deactivating already removes it from the classifier,
#: which reads ``is_active`` only.
RETIRED_CATEGORIES: tuple[str, ...] = ("Pessoa", "Localidade", "Instituição")


def upgrade() -> None:
    """
    Swaps the subject vocabulary for the one measured against the real collection.

    Two statements, deliberately kept apart:

    1. The eight drawers the classification runs against are registered (idempotent, so a
       database that already has some of them converges instead of failing).
    2. ``Pessoa``, ``Localidade`` and ``Instituição`` are deactivated. The first was empty;
       the other two held 58 and 113 tags of geography and provenance that are not subjects
       and now belong to the ``archive_tag_facets`` axis.

    The tags pointing at a retired drawer are detached, and **that is what re-queues them**:
    the worker only ever classifies tags whose ``macro_category_id IS NULL``, so a tag left
    pointing at an inactive drawer would be stuck forever — visible in the UI as belonging to
    a drawer the classifier no longer considers. Detaching is not a reclassification: the
    worker decides the new drawer, and every tag it rewrites was already wrong.

    The description of each drawer stays as curator-facing documentation and is deliberately
    **not** sent to the model — the same rule the repository enforced for the previous
    vocabulary, guarded by its own test.
    """
    connection = op.get_bind()

    for name, description in SUBJECT_CATEGORIES:
        connection.execute(
            sa.text(
                """
                INSERT INTO archive_macro_categories (name, description, is_active)
                VALUES (:name, :description, true)
                ON CONFLICT (name) DO UPDATE
                    SET description = EXCLUDED.description,
                        is_active = true
                """
            ),
            {"name": name, "description": description},
        )

    connection.execute(
        sa.text("UPDATE archive_macro_categories SET is_active = false WHERE name = ANY(:names)"),
        {"names": list(RETIRED_CATEGORIES)},
    )

    connection.execute(
        sa.text(
            """
            UPDATE archive_tags
               SET macro_category_id = NULL,
                   ai_confidence_score = NULL
             WHERE macro_category_id IN (
                   SELECT category_id FROM archive_macro_categories
                    WHERE is_active = false
             )
            """
        )
    )


def downgrade() -> None:
    """
    Restores the previous drawers as the active vocabulary.

    The tags detached by the upgrade are **not** restored to their previous drawer: that
    mapping is not recorded anywhere, and inventing it would be worse than leaving them
    orphan. They return to the queue and the restored vocabulary reclassifies them, which is
    the same path every other pending tag takes.
    """
    connection = op.get_bind()

    connection.execute(
        sa.text("UPDATE archive_macro_categories SET is_active = true WHERE name = ANY(:names)"),
        {"names": list(RETIRED_CATEGORIES)},
    )
    connection.execute(
        sa.text("UPDATE archive_macro_categories SET is_active = false WHERE name = ANY(:names)"),
        {"names": [name for name, _description in SUBJECT_CATEGORIES]},
    )

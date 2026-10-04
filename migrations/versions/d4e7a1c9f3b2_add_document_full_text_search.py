"""add document full text search vector

Revision ID: d4e7a1c9f3b2
Revises: 2f86264b563b
Create Date: 2026-10-03 21:26:28.000000

Replaces the dead ``semantic_search_vector`` text column with a native PostgreSQL
full-text search vector. The vector is a ``GENERATED ... STORED`` column, so it is
always consistent with the document text (including after a human review) and no
worker or idempotency stamp is needed to keep it fresh.

The ``portuguese`` dictionary alone is not reliably accent-insensitive
(``gaucho`` does not find ``Gaúcho``), so the expression is wrapped in
``immutable_unaccent``. ``unaccent(regdictionary, text)`` is STABLE and therefore
illegal inside a generated column / index expression; the wrapper pins the fixed
dictionary and is declared IMMUTABLE on purpose. The only thing that would
invalidate that promise is changing the unaccent dictionary, which no migration does.

``testing/conftest.py`` creates the same extension and function before
``Base.metadata.create_all`` because the test database is built from the models.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e7a1c9f3b2"
down_revision: str | Sequence[str] | None = "2f86264b563b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


IMMUTABLE_UNACCENT_SQL = """
CREATE OR REPLACE FUNCTION public.immutable_unaccent(txt text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, txt) $$;
"""

# Keep byte-identical to ``DOCUMENT_SEARCH_VECTOR_SQL`` in
# ``memoria_curitibana/domains/archive/models/document.py``.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('portuguese', public.immutable_unaccent("
    "coalesce(final_title, '') || ' ' || coalesce(original_title, ''))), 'A')"
    " || "
    "setweight(to_tsvector('portuguese', public.immutable_unaccent("
    "coalesce(scope_content, '') || ' ' || coalesce(admin_bio_history, '') || ' ' || coalesce(provenance, ''))), 'B')"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(IMMUTABLE_UNACCENT_SQL)

    op.drop_column("archive_documents", "semantic_search_vector")
    op.execute(
        f"ALTER TABLE archive_documents ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({SEARCH_VECTOR_SQL}) STORED"
    )
    op.create_index(
        "ix_archive_documents_search_vector",
        "archive_documents",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_archive_documents_search_vector", table_name="archive_documents", postgresql_using="gin")
    op.drop_column("archive_documents", "search_vector")
    op.add_column("archive_documents", sa.Column("semantic_search_vector", sa.Text(), nullable=True))
    op.execute("DROP FUNCTION IF EXISTS public.immutable_unaccent(text)")

"""add document embeddings

Revision ID: e7b2c4a91d38
Revises: d4e7a1c9f3b2
Create Date: 2026-10-03 22:05:00.000000

Adds the semantic-search vector produced by the ``embedding`` worker. The dimension
is fixed by the ``multilingual_minilm`` engine preset (``paraphrase-multilingual-
MiniLM-L12-v2``, 384); a unit test guards the pair, because changing the model means a
new column dimension and a re-embedding of the whole collection.

The index is HNSW with cosine distance: unlike IVFFlat it needs no training data and
keeps recall high as the collection grows.

``testing/conftest.py`` creates the ``vector`` extension before
``Base.metadata.create_all`` because the test database is built from the models.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b2c4a91d38"
down_revision: str | Sequence[str] | None = "d4e7a1c9f3b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Keep in sync with ``EMBEDDING_DIMENSIONS`` in
# ``scrinalia/domains/archive/models/document.py``.
EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"ALTER TABLE archive_documents ADD COLUMN embedding vector({EMBEDDING_DIMENSIONS})")
    op.create_index(
        "ix_archive_documents_embedding",
        "archive_documents",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_archive_documents_embedding", table_name="archive_documents", postgresql_using="hnsw")
    op.execute("ALTER TABLE archive_documents DROP COLUMN embedding")

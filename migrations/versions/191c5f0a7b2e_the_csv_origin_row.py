"""Seed the ``csv`` origin row.

The origin is a definition in code plus a row in ``ingestion_origins`` (ADR 0016). The import route
checks the row and refuses with a sentence when it is absent, so an installation upgraded from an
earlier release needs the row before the card can import anything. Inserting is idempotent: a
deployment that already created the row by hand keeps its lifecycle and configuration.

Revision ID: 191c5f0a7b2e
Revises: 71a2b4c6d8e0
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "191c5f0a7b2e"
down_revision: str | Sequence[str] | None = "71a2b4c6d8e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four names dynamically; listing them keeps CodeQL's unused-global rule (and
#: any reader) from treating the migration's own identifiers as dead code. Every migration in this
#: repository does the same.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Adds the CSV origin, enabled, with no adapter configuration and no agenda."""
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO ingestion_origins (code, enabled, config, options)
            VALUES (:code, :enabled, CAST(:config AS jsonb), CAST(:options AS jsonb))
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {"code": "csv", "enabled": True, "config": json.dumps({}), "options": json.dumps({})},
    )


def downgrade() -> None:
    """Removes the row the upgrade added; its raw and staging rows keep their provenance string."""
    op.get_bind().execute(sa.text("DELETE FROM ingestion_origins WHERE code = :code"), {"code": "csv"})

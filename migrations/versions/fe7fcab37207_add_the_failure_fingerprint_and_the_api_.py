"""add the failure fingerprint and the api error ledger

Two halves of one question — *what is breaking, and how often?*

``archive_worker_runs.error_fingerprint`` groups the executions ledger by root cause, and
``archive_api_errors`` is what lets the API's own unexpected failures be read the same way. Both
carry the **same** generated column, computed by the same function, so a cause that breaks a worker
and a request is one line on the failures screen instead of two unrelated ones.

The fingerprint is a generated column and not one written by the application, and that is the whole
point: ``ADD COLUMN ... GENERATED ALWAYS AS (...) STORED`` computes the value for the rows that
already exist while it rewrites the table, so the backfill *is* the column addition and there is
exactly one definition of the normalization — it cannot drift from the code that writes the message.
A Python backfill here would have been a second definition, and importing application code into a
migration is a dependency this repository has nowhere else.

The function is mirrored in ``testing/conftest.py``, exactly like ``immutable_unaccent``: the test
schema is built by ``Base.metadata.create_all`` and not by Alembic, so the function has to exist
before ``create_all`` emits the generated column that calls it.

The error text is expected to begin with the exception's class (``ValueError: ...``); the ledger's
writer guarantees it. ``str(exc)`` alone would let two different failures with the same sentence
share a fingerprint.

Revision ID: fe7fcab37207
Revises: 6414e7d6ca06
Create Date: 2026-10-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fe7fcab37207"
down_revision: str | None = "6414e7d6ca06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The one definition of "root cause", used by both generated columns below. It has to be SQL: a
#: generated column can only call an ``IMMUTABLE`` function, and a Python implementation would have
#: to be duplicated here to backfill. ``STRICT`` is what keeps a ``NULL`` error a ``NULL``
#: fingerprint instead of an empty string.
#:
#: The order of the substitutions matters. The UUID is consumed before the digit rule can shred it,
#: and the long-hex rule before the plain-digit one for the same reason. The path rule runs last and
#: stops at a quote on purpose, so ``'.../thumb_4821.jpg'`` becomes ``'<path>'`` and not ``'<path>``.
ERROR_FINGERPRINT_FUNCTION_SQL = r"""
CREATE OR REPLACE FUNCTION public.archive_error_fingerprint(message text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$
  SELECT left(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace(
            lower(btrim(regexp_replace(split_part(message, E'\n', 1), '\s+', ' ', 'g'))),
            '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>', 'g'
          ),
          '[0-9a-f]{16,}', '<hash>', 'g'
        ),
        '[0-9]+', '<n>', 'g'
      ),
      '(/[^ /"'']+)+', '<path>', 'g'
    ),
    200
  )
$$;
"""

#: The expression of both generated columns, spelled with the schema because that is how PostgreSQL
#: reflects it back — without ``public.`` ``alembic check`` would report a difference that is not one.
FINGERPRINT_EXPRESSION = "public.archive_error_fingerprint({column})"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(ERROR_FINGERPRINT_FUNCTION_SQL)

    op.add_column(
        "archive_worker_runs",
        sa.Column(
            "error_fingerprint",
            sa.Text(),
            sa.Computed(FINGERPRINT_EXPRESSION.format(column="error"), persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_worker_run_error_fingerprint", "archive_worker_runs", ["error_fingerprint"])

    op.create_table(
        "archive_api_errors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=400), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "error_fingerprint",
            sa.Text(),
            sa.Computed(FINGERPRINT_EXPRESSION.format(column="message"), persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_error_occurred_at", "archive_api_errors", ["occurred_at"])
    op.create_index("ix_api_error_fingerprint", "archive_api_errors", ["error_fingerprint"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_api_error_fingerprint", table_name="archive_api_errors")
    op.drop_index("ix_api_error_occurred_at", table_name="archive_api_errors")
    op.drop_table("archive_api_errors")

    op.drop_index("ix_worker_run_error_fingerprint", table_name="archive_worker_runs")
    op.drop_column("archive_worker_runs", "error_fingerprint")

    op.execute("DROP FUNCTION IF EXISTS public.archive_error_fingerprint(text)")

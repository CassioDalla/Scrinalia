"""the origin is a first-class object: its table, its provenance and its slot

ADR 0008 made the origin a parameter; #44 makes it an object. This migration adds the table that
holds an origin's lifecycle, configuration and agenda, and the ``origin_code`` columns that carry
the provenance from the queue to the archive and to the run ledger.

Three decisions worth recording:

* **The business key of a record stays ``description_id``.** The origin is provenance, not identity:
  an adapter that can collide with another namespaces its own ids. Making the pair
  ``(origin_code, description_id)`` the key would touch every foreign key and the archive's primary
  key, for a collision no shipped origin produces.
* **The concurrency guard includes the origin.** ``uq_worker_run_active`` was
  ``(worker_name) WHERE status IN ('QUEUED','RUNNING')``; it becomes
  ``(worker_name, COALESCE(origin_code, ''))`` with the same predicate. The archive workers keep
  their one-slot-per-worker guarantee (their origin is NULL and coalesces to one value), while each
  ingestion origin gets a slot of its own. The job is the same ``ingestion`` worker for all origins,
  so without this the second origin would be refused while the first crawled.
* **The legacy rows are the reference origin.** The only origin the package shipped before this
  change was ``pmc``; the migration attributes the existing queue/raw/staging/archive rows to it
  instead of leaving a NULL that the panel would have to explain. A deployment that ran another
  origin can correct the rows; the alternative, reading ``ACERVO_SOURCE`` at migration time, would
  make the migration depend on an environment variable that is being removed.

Revision ID: 44a1b2c3d4e5
Revises: d72c0a4b1e9f
Create Date: 2026-10-25 15:10:00.000000

"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "44a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "d72c0a4b1e9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The reference origin the rows written before plural ingestion belonged to.
LEGACY_ORIGIN = "pmc"


def _seed_origins() -> None:
    """
    Inserts the two origins the package ships, with the deployment's own URLs when it has them.

    The reference adapter still accepts ``PUBLIC_SCRAPE_*`` as a fallback, so an existing ``.env``
    keeps working even if this insert stores no URL; storing them here is what makes the new row the
    operator's to edit on the screen. ``manual`` has no adapter configuration at all.
    """
    from scrinalia.core.config import get_settings

    settings = get_settings()
    pmc_config = {
        key: value
        for key, value in {
            "base_url": settings.PUBLIC_SCRAPE_URL,
            "detail_url": settings.PUBLIC_SCRAPE_DETAIL_URL,
        }.items()
        if value
    }
    bind = op.get_bind()
    statement = sa.text(
        """
        INSERT INTO ingestion_origins (code, enabled, config, options)
        VALUES (:code, :enabled, CAST(:config AS jsonb), CAST(:options AS jsonb))
        ON CONFLICT (code) DO NOTHING
        """
    )
    for code, enabled, config in (
        ("pmc", True, pmc_config),
        ("manual", True, {}),
    ):
        bind.execute(
            statement,
            {"code": code, "enabled": enabled, "config": json.dumps(config), "options": json.dumps({})},
        )


def upgrade() -> None:
    """Creates the origin table, the provenance columns and the per-origin slot."""
    op.create_table(
        "ingestion_origins",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cron", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index("ix_ingestion_origin_next_run_at", "ingestion_origins", ["next_run_at"])

    op.add_column("scraping_queue", sa.Column("origin_code", sa.String(length=50), nullable=True))
    op.create_index("ix_scraping_queue_origin_code", "scraping_queue", ["origin_code"])
    op.create_index("ix_scraping_queue_origin_last_scraped", "scraping_queue", ["origin_code", "last_scraped_at"])

    op.add_column("raw_data", sa.Column("origin_code", sa.String(length=50), nullable=True))
    op.add_column("raw_data", sa.Column("created_by", sa.String(length=120), nullable=True))
    op.add_column("raw_data", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_raw_data_created_by_user_id",
        "raw_data",
        "auth_users",
        ["created_by_user_id"],
        ["user_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_raw_data_origin_code", "raw_data", ["origin_code"])
    op.create_index("ix_raw_data_origin_description", "raw_data", ["origin_code", "description_id"])

    op.add_column("staging_documents", sa.Column("origin_code", sa.String(length=50), nullable=True))
    op.create_index("ix_staging_documents_origin_code", "staging_documents", ["origin_code"])

    op.add_column("archive_documents", sa.Column("origin_code", sa.String(length=50), nullable=True))
    op.create_index("ix_archive_documents_origin_code", "archive_documents", ["origin_code"])

    op.add_column("archive_worker_runs", sa.Column("origin_code", sa.String(length=50), nullable=True))
    op.create_index("ix_archive_worker_runs_origin_code", "archive_worker_runs", ["origin_code"])

    op.drop_index("uq_worker_run_active", table_name="archive_worker_runs")
    op.create_index(
        "uq_worker_run_active",
        "archive_worker_runs",
        ["worker_name", sa.text("COALESCE(origin_code, '')")],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )

    # The reference deployment's rows were all read from the one origin the package shipped.
    for table in ("scraping_queue", "raw_data", "staging_documents", "archive_documents"):
        op.execute(
            sa.text(f"UPDATE {table} SET origin_code = :code WHERE origin_code IS NULL").bindparams(code=LEGACY_ORIGIN)
        )

    _seed_origins()


def downgrade() -> None:
    """
    Drops the provenance and the table, and restores the worker-only slot.

    The backfill is not reversed: the rows that were NULL before the upgrade cannot be told apart
    from the rows this migration attributed to the reference origin. The origin's agenda and
    configuration are operational, not archival; the ledger rows themselves stay.
    """
    op.drop_index("uq_worker_run_active", table_name="archive_worker_runs")
    op.create_index(
        "uq_worker_run_active",
        "archive_worker_runs",
        ["worker_name"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )

    op.drop_index("ix_archive_worker_runs_origin_code", table_name="archive_worker_runs")
    op.drop_column("archive_worker_runs", "origin_code")

    op.drop_index("ix_archive_documents_origin_code", table_name="archive_documents")
    op.drop_column("archive_documents", "origin_code")

    op.drop_index("ix_staging_documents_origin_code", table_name="staging_documents")
    op.drop_column("staging_documents", "origin_code")

    op.drop_index("ix_raw_data_origin_description", table_name="raw_data")
    op.drop_index("ix_raw_data_origin_code", table_name="raw_data")
    op.drop_constraint("fk_raw_data_created_by_user_id", "raw_data", type_="foreignkey")
    op.drop_column("raw_data", "created_by_user_id")
    op.drop_column("raw_data", "created_by")
    op.drop_column("raw_data", "origin_code")

    op.drop_index("ix_scraping_queue_origin_last_scraped", table_name="scraping_queue")
    op.drop_index("ix_scraping_queue_origin_code", table_name="scraping_queue")
    op.drop_column("scraping_queue", "origin_code")

    op.drop_index("ix_ingestion_origin_next_run_at", table_name="ingestion_origins")
    op.drop_table("ingestion_origins")

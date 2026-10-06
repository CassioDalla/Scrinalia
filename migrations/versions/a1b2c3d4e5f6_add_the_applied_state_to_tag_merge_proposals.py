"""add the APPLIED state to the tag merge proposals

The catalogue kept a proposal at ``APPROVED`` forever, even after its cluster had been absorbed.
The archivist saw a queue of approvals that could not be applied again — clicking apply produced
"os membros já não existem no acervo" for every row — and the finished batch looked like a failure.

``APPLIED`` is the state the write should have written all along: the decision (who approved, when)
stays in ``decided_by``/``decided_at``, and the *when* of the write lives in the merge ledger.

The migration also repairs the rows the old code left behind, in two steps. A proposal whose
fingerprint appears in the ledger with no ``undone_at`` **was** applied through the batch, and is
marked as such. A merge that was undone does not count, because the tags it absorbed are back.

The second step catches the clusters that were applied *without* a proposal — the merges made through
``POST /tags/merge``, whose ledger rows carry no fingerprint. There the evidence is the names: if
every member besides the canonical is gone **and** the ledger records it as absorbed (not undone),
the cluster was fulfilled. Requiring the ledger entry is what keeps this honest: a tag removed by the
stopword purge also leaves no member behind, and calling that "applied" would be a lie.

Revision ID: a1b2c3d4e5f6
Revises: 3d62b30c117b
Create Date: 2026-10-05

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "3d62b30c117b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "chk_tag_merge_proposal_status"
BEFORE = "status IN ('SUGGESTED', 'APPROVED', 'REJECTED')"
AFTER = "status IN ('SUGGESTED', 'APPROVED', 'REJECTED', 'APPLIED')"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "archive_tag_merge_proposals", type_="check")
    op.create_check_constraint(CONSTRAINT, "archive_tag_merge_proposals", AFTER)

    # Applied through the batch: the ledger row carries the proposal's fingerprint.
    op.execute(
        """
        UPDATE archive_tag_merge_proposals AS p
           SET status = 'APPLIED'
         WHERE p.status = 'APPROVED'
           AND EXISTS (
                 SELECT 1
                   FROM archive_taxonomy_merge_log AS l
                  WHERE l.cluster_fingerprint = p.fingerprint
                    AND l.undone_at IS NULL
           )
        """
    )

    # Applied through the plain merge route: no fingerprint, so the evidence is the names — every
    # member besides the canonical is gone and the ledger says where it went.
    op.execute(
        """
        UPDATE archive_tag_merge_proposals AS p
           SET status = 'APPLIED'
         WHERE p.status = 'APPROVED'
           AND p.canonical_id IS NOT NULL
           AND EXISTS (SELECT 1 FROM jsonb_array_elements(p.members) AS m)
           AND NOT EXISTS (
                 SELECT 1
                   FROM jsonb_array_elements(p.members) AS m
                  WHERE (m->>'tag_id')::int <> p.canonical_id
                    AND EXISTS (SELECT 1 FROM archive_tags AS t WHERE t.tag_id = (m->>'tag_id')::int)
           )
           AND NOT EXISTS (
                 SELECT 1
                   FROM jsonb_array_elements(p.members) AS m
                  WHERE (m->>'tag_id')::int <> p.canonical_id
                    AND NOT EXISTS (
                          SELECT 1
                            FROM archive_taxonomy_merge_log AS l
                           WHERE l.absorbed_name = lower(m->>'name')
                             AND l.canonical_id = p.canonical_id
                             AND l.undone_at IS NULL
                    )
           )
        """
    )


def downgrade() -> None:
    # Everything applied becomes approved again: the old schema had nowhere else to put it.
    op.execute("UPDATE archive_tag_merge_proposals SET status = 'APPROVED' WHERE status = 'APPLIED'")
    op.drop_constraint(CONSTRAINT, "archive_tag_merge_proposals", type_="check")
    op.create_check_constraint(CONSTRAINT, "archive_tag_merge_proposals", BEFORE)

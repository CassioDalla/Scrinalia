"""enforce one row per normalized entity and tag name

``normalize_entity``/``normalize_tag`` have always been ``strip().lower()``, and every write path
stores the normalized spelling, but the uniqueness the schema enforced was case-sensitive
(``ix_archive_entities_name``). A row in Title Case and the lowercase row for the same name were
therefore two rows, and ``get_or_create_entities`` — which inserts the lowercase spelling and looks
the existing ids up with ``name IN (…lowercase…)`` — could never see the Title Case one. On the
reference collection that produced 3 523 twin groups out of 8 322 entities: every group pairs a June
row (Title Case) with a 2026-10-06 row (lowercase), and 273 further Title Case rows carry no twin.

The migration does two things, in this order because the second is impossible before the first:
reconcile the groups the case-sensitive index allowed, then enforce the rule the normalizer declares
with a unique index on ``lower(btrim(name))``. The tag table carries the same index here too:
measured 0 non-normalized names and 0 collision groups, so it moves no data — but the uniqueness it
relies on is the same shape, and leaving it case-sensitive left the twin defect latent there.

The survivor of a group is the row the collection already uses most (most document links), then the
spelling that is already normalized, then the lowest id, so the outcome does not depend on physical
order. The absorbed row's links are moved with ``ON CONFLICT DO NOTHING`` (a description that
carried both rows keeps one link), its spellings are moved to the survivor before the delete — the
FK is ``ON DELETE CASCADE`` — and then **every** remaining name is normalized, the 273 twin-less
Title Case rows included: a row the insert path cannot find by its own key is the same defect.

The reconciliation is deliberately irreversible. Where the losers went is recorded nowhere once they
are gone, and that is what the curation guide already states for an entity merge: there is no undo.
``downgrade`` drops the two indexes; it does not resurrect the absorbed rows. The conflict ledger
and the review queue keep their snapshots untouched: they are a record of a decision, not a
reference to a row that has to still exist.

Revision ID: b8f066a47e7c
Revises: e927d97c72a9
Create Date: 2026-10-12 10:18:07.567166

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8f066a47e7c"
down_revision: str | Sequence[str] | None = "e927d97c72a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The groups the case-sensitive unique index allowed, keyed by the identity rule itself.
#: ``ON COMMIT DROP`` so the scratch table cannot outlive the migration.
_BUILD_TWIN_MAP = """
CREATE TEMP TABLE _archive_entity_twin_map ON COMMIT DROP AS
WITH ranked AS (
    SELECT entity.entity_id,
           lower(btrim(entity.name)) AS key,
           row_number() OVER (
               PARTITION BY lower(btrim(entity.name))
               ORDER BY (SELECT count(*)
                           FROM archive_document_entities link
                          WHERE link.entity_id = entity.entity_id) DESC,
                        (entity.name = lower(btrim(entity.name))) DESC,
                        entity.entity_id
           ) AS rank
      FROM archive_entities entity
)
SELECT loser.entity_id AS loser_id, survivor.entity_id AS survivor_id
  FROM ranked loser
  JOIN ranked survivor ON survivor.key = loser.key AND survivor.rank = 1
 WHERE loser.rank > 1
"""

#: The absorbed links move to the survivor; a description that carried both keeps its single link.
_MOVE_LINKS = """
INSERT INTO archive_document_entities (description_id, entity_id)
SELECT link.description_id, twin.survivor_id
  FROM archive_document_entities link
  JOIN _archive_entity_twin_map twin ON twin.loser_id = link.entity_id
ON CONFLICT DO NOTHING
"""

#: The spellings already absorbed by the row being deleted have to move before the delete, because
#: ``domain_synonyms.canonical_entity_id`` is ``ON DELETE CASCADE``.
_MOVE_SYNONYMS = """
UPDATE domain_synonyms synonym
   SET canonical_entity_id = twin.survivor_id
  FROM _archive_entity_twin_map twin
 WHERE synonym.canonical_entity_id = twin.loser_id
"""

_DELETE_LOSERS = """
DELETE FROM archive_entities entity
 USING _archive_entity_twin_map twin
 WHERE entity.entity_id = twin.loser_id
"""

#: After the losers are gone every remaining name is unique when normalized, so this cannot collide.
_NORMALIZE_NAMES = """
UPDATE archive_entities
   SET name = lower(btrim(name))
 WHERE name <> lower(btrim(name))
"""


def upgrade() -> None:
    """Reconcile the twin groups, then enforce the normalized identity on both vocabularies."""
    connection = op.get_bind()

    connection.execute(sa.text(_BUILD_TWIN_MAP))
    connection.execute(sa.text(_MOVE_LINKS))
    connection.execute(sa.text(_MOVE_SYNONYMS))
    connection.execute(sa.text(_DELETE_LOSERS))
    connection.execute(sa.text(_NORMALIZE_NAMES))

    op.create_index(
        "uix_archive_entities_name_normalized",
        "archive_entities",
        [sa.text("lower(btrim(name))")],
        unique=True,
    )
    op.create_index(
        "uix_archive_tags_name_normalized",
        "archive_tags",
        [sa.text("lower(btrim(name))")],
        unique=True,
    )


def downgrade() -> None:
    """Drops the rule. The rows the upgrade reconciled stay reconciled: there is no undo."""
    op.drop_index("uix_archive_tags_name_normalized", table_name="archive_tags")
    op.drop_index("uix_archive_entities_name_normalized", table_name="archive_entities")

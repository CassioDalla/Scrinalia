"""
The single definition of the ``domain_synonyms`` upsert.

Both axes write the spelling dictionary through one multi-row
``INSERT ... ON CONFLICT DO UPDATE``, and both used to build that command in their own
repository. One definition here is what keeps the entity path and the tag path from drifting
apart again, and it is also where the defect that aborted a merge is closed: PostgreSQL refuses
a command that would touch the same ``(synonym_name, category)`` conflict target twice, and two
absorbed spellings that differ only in case or in surrounding space collapse to one key through
:func:`normalize_synonym`.
"""

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from scrinalia.domains.archive.domain.normalization import normalize_synonym
from scrinalia.domains.archive.models import DomainSynonyms
from scrinalia.domains.archive.schemas.command_schema import SynonymCommand


def upsert_synonyms(db: Session, synonyms_data: Sequence[SynonymCommand]) -> None:
    """
    Registers the spellings the ingestion and the extraction must redirect to a canonical row.

    Upsert, not ``on_conflict_do_nothing``: when a canonical is absorbed into another one, a
    spelling that already had a mapping has to *move*. Silently keeping the old target made a
    re-merge look successful while changing nothing, and left the extraction pointing at a row
    that no longer exists. Same defect and same fix on both axes.

    The commands are collapsed by ``(synonym_name, category)`` before the insert, and the last
    command for a key wins. A merge can absorb two entities or tags whose names normalize to the
    same key (``"A. B. Deter"`` and ``"a. b. deter"``), exactly like the rename branch can append
    the old canonical name to a list that already carries it: any of those would put the same
    conflict target in the command twice, PostgreSQL answers ``CardinalityViolation`` and the whole
    write aborts — a merge answered 500 and nothing was absorbed. Collapsing in the caller would
    have fixed one caller; collapsing here is what closes the write.
    """
    if not synonyms_data:
        return

    rows: dict[tuple[str, str], dict[str, object]] = {}
    for item in synonyms_data:
        name = normalize_synonym(item.synonym_name)
        rows[(name, item.category)] = {
            "synonym_name": name,
            "category": item.category,
            "canonical_tag_id": item.canonical_tag_id,
            "canonical_entity_id": item.canonical_entity_id,
        }

    stmt = insert(DomainSynonyms).values(list(rows.values()))
    stmt = stmt.on_conflict_do_update(
        index_elements=["synonym_name", "category"],
        set_={
            "canonical_tag_id": stmt.excluded.canonical_tag_id,
            "canonical_entity_id": stmt.excluded.canonical_entity_id,
        },
    )
    db.execute(stmt)

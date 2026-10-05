"""Regression guards for the trigram joins.

Three bugs lived here, and all three were invisible to a green build and to the tests that existed:

1. a redundant ``OR lower(t.name) = lower(e.name)`` in the cross-domain conflict join, which turned
   the join into a ``Join Filter`` and cost a factor of 37 (52.9 s → 1.4 s on the real collection);
2. an ``abs(length(a) - length(b)) <= 3`` prefilter in front of ``%`` in both
   ``find_all_similar_pairs``, which discarded 52-65% of the real duplicate pairs;
3. the belief that a column-to-column ``%`` cannot use the GIN index at all — it can, as long as it
   is the *only* predicate, because PostgreSQL pushes the outer row down as a bitmap index key.

These tests pin the reasoning rather than the timing: a timing assertion would be flaky, and a plan
assertion is useless at fixture scale, where the planner correctly prefers a sequential scan.
"""

from sqlalchemy import event, text

from memoria_curitibana.domains.archive.models import ArchiveEntity, ArchiveTag
from memoria_curitibana.domains.archive.repository import EntityRepository, TagRepository


def _capture_sql(db_session, callback) -> list[str]:
    """Runs ``callback`` and returns every statement SQLAlchemy sent to the database."""
    statements: list[str] = []
    bind = db_session.get_bind()

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", record)
    try:
        callback()
    finally:
        event.remove(bind, "before_cursor_execute", record)

    return statements


# ==========================================
# THE ASSUMPTION THE FIX RESTS ON
# ==========================================


def test_pg_trgm_similarity_is_case_insensitive(use_test_db, db_session):
    """
    This is *why* the removed ``lower() = lower()`` disjunct was redundant, not a safety net.

    ``pg_trgm`` normalises case before extracting trigrams, so a case-only difference scores a
    similarity of exactly 1 — which satisfies the operator at **any** threshold in ``[0, 1]``. If a
    future PostgreSQL changed that, the disjunct would stop being redundant and this test would be
    the thing that says so, instead of a silent loss of conflicts.
    """
    assert db_session.scalar(text("SELECT similarity('Batel', 'batel')")) == 1
    assert db_session.scalar(text("SELECT similarity('IPTU', 'iptu')")) == 1

    # ...and the operator agrees at the strictest possible threshold.
    db_session.execute(text("SET LOCAL pg_trgm.similarity_threshold = 1.0"))
    assert db_session.scalar(text("SELECT 'Batel'::text % 'batel'::text")) is True


def test_the_conflict_join_carries_no_lower_comparison(use_test_db, db_session):
    """
    The structural guard, and the only test here that would have caught the original bug.

    The behavioural test above/below passes with *and* without the redundant disjunct — that is
    precisely what "redundant" means — so it cannot protect the index usage. What can is asserting
    that the emitted join has no ``lower(`` in it: the disjunct is the regression, and this is its
    signature.
    """
    db_session.add_all([ArchiveTag(name="batel"), ArchiveEntity(name="Batel", entity_type="LOC")])
    db_session.flush()

    statements = _capture_sql(
        db_session, lambda: EntityRepository(db_session).get_cross_domain_conflicts(threshold=0.85)
    )

    joins = [statement for statement in statements if "archive_tags" in statement and "archive_entities" in statement]
    assert joins, "a query de conflito não foi emitida"
    for statement in joins:
        assert "lower(" not in statement.lower(), (
            "O join de conflito voltou a comparar lower(name) com lower(name). Isso transforma o "
            "join num Join Filter, o planejador materializa o lado interno e a query passa de 1,4 s "
            "para 52,9 s — com resultado idêntico. Ver o docstring de get_cross_domain_conflicts."
        )


def test_a_case_variant_conflict_is_still_found(use_test_db, db_session):
    """Removing the disjunct must not cost a single conflict: this is the pair it used to cover."""
    db_session.add_all(
        [
            ArchiveTag(name="batel"),
            ArchiveEntity(name="BATEL", entity_type="LOC"),
            ArchiveTag(name="ofício"),
            ArchiveEntity(name="David Carneiro", entity_type="PER"),
        ]
    )
    db_session.flush()

    conflicts = EntityRepository(db_session).get_cross_domain_conflicts(threshold=0.85)

    assert [(conflict.tag_name, conflict.entity_name) for conflict in conflicts] == [("batel", "BATEL")]


# ==========================================
# THE PREFILTER THAT ATE REAL PAIRS
# ==========================================


def test_a_tag_pair_differing_in_length_is_found(use_test_db, db_session):
    """
    Length difference is **not** bounded by trigram similarity.

    ``Avenida Nossa Senhora Da Luz`` (28) and ``Av. Avenida Nossa Senhora Da Luz`` (32) differ by 4
    and score 0.966 — a real duplication, and one the removed prefilter hid. The longer the
    spelling, the more the prefilter threw away.
    """
    db_session.add_all(
        [
            ArchiveTag(name="Avenida Nossa Senhora Da Luz"),
            ArchiveTag(name="Av. Avenida Nossa Senhora Da Luz"),
        ]
    )
    db_session.flush()

    pairs = TagRepository(db_session).find_all_similar_pairs(threshold=0.65)

    assert {(pair.name_1, pair.name_2) for pair in pairs} == {
        ("Avenida Nossa Senhora Da Luz", "Av. Avenida Nossa Senhora Da Luz")
    }


def test_an_entity_pair_differing_in_length_is_found(use_test_db, db_session):
    """The same defect and the same fix on the entity axis."""
    db_session.add_all(
        [
            ArchiveEntity(name="Vila De Ofícios Trindade", entity_type="LOC"),
            ArchiveEntity(name="Vila De Ofícios Vila Trindade", entity_type="LOC"),
        ]
    )
    db_session.flush()

    pairs = EntityRepository(db_session).find_all_similar_pairs(threshold=0.65)

    assert {(pair.name_1, pair.name_2) for pair in pairs} == {
        ("Vila De Ofícios Trindade", "Vila De Ofícios Vila Trindade")
    }


def test_the_similarity_pair_scan_carries_no_length_prefilter(use_test_db, db_session):
    """
    The structural guard for the second bug, on both axes.

    A behavioural test only covers the spellings it happens to use; this asserts the shape of the
    query, so any prefilter that narrows ``%`` is refused, whatever it is called.
    """
    db_session.add_all([ArchiveTag(name="rua xv de novembro"), ArchiveTag(name="rua xv novembro")])
    db_session.flush()

    statements = _capture_sql(db_session, lambda: TagRepository(db_session).find_all_similar_pairs(threshold=0.65))
    pairs_sql = [statement for statement in statements if "archive_tags" in statement]

    assert pairs_sql, "a varredura de pares não foi emitida"
    for statement in pairs_sql:
        assert "length(" not in statement.lower(), (
            "Voltou um prefilter de comprimento na frente de '%'. Ele não filtra candidatos: ele "
            "descarta pares reais (419 de 647 medidos) e não é preciso para a performance — o "
            "índice GIN já é o filtro."
        )

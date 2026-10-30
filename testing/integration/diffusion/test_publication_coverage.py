"""The coverage predicate against the test database: the view is the definition (ADR 0023).

The tests build the arrangement by hand — ``path`` is materialised and the view reads it — and then
ask the repository the same question the page and the public surface ask. A test here failing is a
record exposed or hidden against the curator's decision, so the cases are the decisions themselves:
the branch, the child approved later, the exclusion, the paused channel and the lookalike id.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrinalia.domains.diffusion.coverage import ARCHIVE_DOCUMENT_CHANNELS as COVERAGE
from scrinalia.domains.diffusion.diffusion_registry import PUBLIC_SITE_CODE
from scrinalia.domains.diffusion.models import DiffusionChannelScope
from scrinalia.domains.diffusion.publication_repository import DiffusionPublicationRepository
from testing.integration.diffusion.publication_helpers import (
    APPROVED,
    a_channel,
    a_node,
    a_scope,
    an_exclusion,
    coverage_of,
)


def test_the_approved_descendants_of_a_published_branch_are_covered(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "serie", parent_id="fundo")
    a_node(db_session, "item", parent_id="serie")
    a_scope(db_session, "fundo")
    db_session.commit()

    assert coverage_of(db_session, "fundo", "serie", "item") == {
        "fundo": [PUBLIC_SITE_CODE],
        "serie": [PUBLIC_SITE_CODE],
        "item": [PUBLIC_SITE_CODE],
    }


def test_a_child_approved_after_the_scope_enters_it_without_a_second_decision(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    child = a_node(db_session, "filho", parent_id="fundo", approved=False)
    a_scope(db_session, "fundo")
    db_session.commit()

    assert "filho" not in coverage_of(db_session, "filho")

    child.review_status = APPROVED
    db_session.commit()

    assert coverage_of(db_session, "filho") == {"filho": [PUBLIC_SITE_CODE]}


def test_a_scope_without_descendants_covers_only_its_node(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "serie", parent_id="fundo")
    a_scope(db_session, "fundo", include_descendants=False)
    db_session.commit()

    assert coverage_of(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}
    assert "serie" not in coverage_of(db_session, "serie")


def test_an_unapproved_record_under_a_scope_is_not_covered(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "pendente", parent_id="fundo", approved=False)
    a_scope(db_session, "fundo")
    db_session.commit()

    assert coverage_of(db_session, "pendente") == {}


def test_an_exclusion_keeps_one_child_out_and_leaves_its_sibling_covered(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    a_node(db_session, "b", parent_id="fundo")
    a_scope(db_session, "fundo")
    an_exclusion(db_session, "b")
    db_session.commit()

    assert coverage_of(db_session, "fundo", "a", "b") == {"fundo": [PUBLIC_SITE_CODE], "a": [PUBLIC_SITE_CODE]}


def test_an_exclusion_over_a_subtree_keeps_all_of_it_out(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "serie", parent_id="fundo")
    a_node(db_session, "item", parent_id="serie")
    a_node(db_session, "outro", parent_id="fundo")
    a_scope(db_session, "fundo")
    an_exclusion(db_session, "serie", include_descendants=True)
    db_session.commit()

    assert coverage_of(db_session, "serie", "item") == {}
    assert coverage_of(db_session, "outro") == {"outro": [PUBLIC_SITE_CODE]}


def test_a_revoked_scope_stops_covering_and_a_new_one_may_be_created(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    first = a_scope(db_session, "fundo")
    db_session.commit()
    assert coverage_of(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}

    first.revoked_at = datetime.now(UTC)
    db_session.commit()
    assert coverage_of(db_session, "fundo") == {}

    a_scope(db_session, "fundo")
    db_session.commit()
    assert coverage_of(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}


def test_a_second_active_scope_on_the_same_node_is_refused(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_scope(db_session, "fundo")
    db_session.flush()

    with pytest.raises(IntegrityError):
        a_scope(db_session, "fundo")
        db_session.flush()
    db_session.rollback()


def test_deleting_the_node_cascades_its_scope(db_session: Session) -> None:
    a_channel(db_session)
    node = a_node(db_session, "avulso")
    a_scope(db_session, "avulso", include_descendants=False)
    db_session.commit()

    db_session.delete(node)
    db_session.commit()

    remaining = db_session.scalars(select(DiffusionChannelScope)).all()
    assert remaining == []
    assert coverage_of(db_session, "avulso") == {}


def test_the_nearest_scope_is_the_origin_of_the_coverage(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "serie", parent_id="fundo")
    a_node(db_session, "item", parent_id="serie")
    a_scope(db_session, "fundo")
    inner = a_scope(db_session, "serie")
    db_session.commit()

    origin = db_session.scalar(
        select(COVERAGE.c.scope_id).where(
            COVERAGE.c.description_id == "item", COVERAGE.c.channel_code == PUBLIC_SITE_CODE
        )
    )
    assert origin == inner.scope_id


def test_a_lookalike_id_is_not_inside_the_branch(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo_a")
    a_node(db_session, "filho_a", parent_id="fundo_a")
    a_node(db_session, "fundoXa")
    a_node(db_session, "filho_x", parent_id="fundoXa")
    a_scope(db_session, "fundo_a")
    db_session.commit()

    assert coverage_of(db_session, "filho_a") == {"filho_a": [PUBLIC_SITE_CODE]}
    assert coverage_of(db_session, "filho_x") == {}


def test_a_paused_channel_keeps_its_coverage(db_session: Session) -> None:
    a_channel(db_session, enabled=False)
    a_node(db_session, "fundo")
    a_scope(db_session, "fundo")
    db_session.commit()

    assert coverage_of(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}


def test_the_counts_are_one_definition_of_the_collection(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "publicado")
    a_node(db_session, "semcanal")
    a_node(db_session, "emrevisao", approved=False)
    a_scope(db_session, "publicado")
    db_session.commit()

    counts = DiffusionPublicationRepository(db_session).counts()

    assert counts.site == 1
    assert counts.in_channels == 1
    assert counts.approved_without_channel == 1
    assert counts.in_review == 1
    assert counts.enabled_channels == 1


def test_the_lists_split_the_covered_from_the_approved_without_channel(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "publicado", title="Publicado")
    a_node(db_session, "semcanal", title="Sem canal")
    a_node(db_session, "emrevisao", approved=False)
    a_scope(db_session, "publicado")
    db_session.commit()
    repository = DiffusionPublicationRepository(db_session)

    covered, covered_total = repository.list_publications(state="covered")
    uncovered, uncovered_total = repository.list_publications(state="uncovered")

    assert [row.description_id for row in covered] == ["publicado"]
    assert covered[0].channels == (PUBLIC_SITE_CODE,)
    assert covered_total == 1
    assert [row.description_id for row in uncovered] == ["semcanal"]
    assert uncovered[0].channels == ()
    assert uncovered_total == 1


def test_the_branch_filter_of_the_lists_reads_the_materialised_path(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "serie", parent_id="fundo")
    a_node(db_session, "fora")
    a_scope(db_session, "serie")
    db_session.commit()
    repository = DiffusionPublicationRepository(db_session)

    covered, total = repository.list_publications(state="covered", node_id="fundo")

    assert [row.description_id for row in covered] == ["serie"]
    assert total == 1


def test_the_scope_list_reports_the_origin_count_and_the_approved_count(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "serie", parent_id="fundo")
    a_node(db_session, "semcanal", parent_id="fundo")
    a_scope(db_session, "fundo")
    db_session.commit()
    repository = DiffusionPublicationRepository(db_session)

    scopes = repository.list_scopes()

    assert len(scopes) == 1
    assert scopes[0].node_id == "fundo"
    assert scopes[0].kind == "INCLUSION"
    assert scopes[0].covered_count == 3
    assert scopes[0].approved_count == 3

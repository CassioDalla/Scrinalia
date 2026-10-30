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

from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.diffusion.coverage import ARCHIVE_DOCUMENT_CHANNELS as COVERAGE
from scrinalia.domains.diffusion.diffusion_registry import PUBLIC_SITE_CODE
from scrinalia.domains.diffusion.models import DiffusionChannel, DiffusionChannelExclusion, DiffusionChannelScope
from scrinalia.domains.diffusion.publication_repository import DiffusionPublicationRepository

APPROVED = ArchiveReviewStatus.HUMAN_APPROVED


def _channel(db: Session, code: str = PUBLIC_SITE_CODE, *, enabled: bool = True) -> DiffusionChannel:
    """The lifecycle row a scope's foreign key needs; the registry does not seed one."""
    row = DiffusionChannel(code=code, enabled=enabled)
    db.add(row)
    db.flush()
    return row


def _node(
    db: Session,
    description_id: str,
    *,
    parent_id: str | None = None,
    approved: bool = True,
    title: str | None = None,
) -> ArchiveDocument:
    """A description with its materialised path and, by default, the approval the coverage requires."""
    parent_path = None
    if parent_id is not None:
        parent_path = db.scalar(select(ArchiveDocument.path).where(ArchiveDocument.description_id == parent_id))
    path = f"{parent_path}.{description_id}" if parent_path else description_id
    doc = ArchiveDocument(
        description_id=description_id,
        original_title=title or description_id,
        staging_content_hash=f"hash_{description_id}",
        parent_id=parent_id,
        path=path,
        review_status=APPROVED if approved else ArchiveReviewStatus.PENDING_AI,
    )
    db.add(doc)
    db.flush()
    return doc


def _scope(
    db: Session,
    node_id: str,
    *,
    channel_code: str = PUBLIC_SITE_CODE,
    include_descendants: bool = True,
) -> DiffusionChannelScope:
    scope = DiffusionChannelScope(channel_code=channel_code, node_id=node_id, include_descendants=include_descendants)
    db.add(scope)
    db.flush()
    return scope


def _exclusion(
    db: Session,
    node_id: str,
    *,
    channel_code: str = PUBLIC_SITE_CODE,
    include_descendants: bool = True,
) -> DiffusionChannelExclusion:
    row = DiffusionChannelExclusion(
        channel_code=channel_code,
        node_id=node_id,
        include_descendants=include_descendants,
        reason="pedido da instituição",
    )
    db.add(row)
    db.flush()
    return row


def _covered(db: Session, *description_ids: str) -> dict[str, list[str]]:
    return DiffusionPublicationRepository(db).coverage_for(list(description_ids))


def test_the_approved_descendants_of_a_published_branch_are_covered(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "serie", parent_id="fundo")
    _node(db_session, "item", parent_id="serie")
    _scope(db_session, "fundo")
    db_session.commit()

    assert _covered(db_session, "fundo", "serie", "item") == {
        "fundo": [PUBLIC_SITE_CODE],
        "serie": [PUBLIC_SITE_CODE],
        "item": [PUBLIC_SITE_CODE],
    }


def test_a_child_approved_after_the_scope_enters_it_without_a_second_decision(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    child = _node(db_session, "filho", parent_id="fundo", approved=False)
    _scope(db_session, "fundo")
    db_session.commit()

    assert "filho" not in _covered(db_session, "filho")

    child.review_status = APPROVED
    db_session.commit()

    assert _covered(db_session, "filho") == {"filho": [PUBLIC_SITE_CODE]}


def test_a_scope_without_descendants_covers_only_its_node(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "serie", parent_id="fundo")
    _scope(db_session, "fundo", include_descendants=False)
    db_session.commit()

    assert _covered(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}
    assert "serie" not in _covered(db_session, "serie")


def test_an_unapproved_record_under_a_scope_is_not_covered(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "pendente", parent_id="fundo", approved=False)
    _scope(db_session, "fundo")
    db_session.commit()

    assert _covered(db_session, "pendente") == {}


def test_an_exclusion_keeps_one_child_out_and_leaves_its_sibling_covered(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "a", parent_id="fundo")
    _node(db_session, "b", parent_id="fundo")
    _scope(db_session, "fundo")
    _exclusion(db_session, "b")
    db_session.commit()

    assert _covered(db_session, "fundo", "a", "b") == {"fundo": [PUBLIC_SITE_CODE], "a": [PUBLIC_SITE_CODE]}


def test_an_exclusion_over_a_subtree_keeps_all_of_it_out(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "serie", parent_id="fundo")
    _node(db_session, "item", parent_id="serie")
    _node(db_session, "outro", parent_id="fundo")
    _scope(db_session, "fundo")
    _exclusion(db_session, "serie", include_descendants=True)
    db_session.commit()

    assert _covered(db_session, "serie", "item") == {}
    assert _covered(db_session, "outro") == {"outro": [PUBLIC_SITE_CODE]}


def test_a_revoked_scope_stops_covering_and_a_new_one_may_be_created(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    first = _scope(db_session, "fundo")
    db_session.commit()
    assert _covered(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}

    first.revoked_at = datetime.now(UTC)
    db_session.commit()
    assert _covered(db_session, "fundo") == {}

    _scope(db_session, "fundo")
    db_session.commit()
    assert _covered(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}


def test_a_second_active_scope_on_the_same_node_is_refused(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _scope(db_session, "fundo")
    db_session.flush()

    with pytest.raises(IntegrityError):
        _scope(db_session, "fundo")
        db_session.flush()
    db_session.rollback()


def test_deleting_the_node_cascades_its_scope(db_session: Session) -> None:
    _channel(db_session)
    node = _node(db_session, "avulso")
    _scope(db_session, "avulso", include_descendants=False)
    db_session.commit()

    db_session.delete(node)
    db_session.commit()

    remaining = db_session.scalars(select(DiffusionChannelScope)).all()
    assert remaining == []
    assert _covered(db_session, "avulso") == {}


def test_the_nearest_scope_is_the_origin_of_the_coverage(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "serie", parent_id="fundo")
    _node(db_session, "item", parent_id="serie")
    _scope(db_session, "fundo")
    inner = _scope(db_session, "serie")
    db_session.commit()

    origin = db_session.scalar(
        select(COVERAGE.c.scope_id).where(
            COVERAGE.c.description_id == "item", COVERAGE.c.channel_code == PUBLIC_SITE_CODE
        )
    )
    assert origin == inner.scope_id


def test_a_lookalike_id_is_not_inside_the_branch(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo_a")
    _node(db_session, "filho_a", parent_id="fundo_a")
    _node(db_session, "fundoXa")
    _node(db_session, "filho_x", parent_id="fundoXa")
    _scope(db_session, "fundo_a")
    db_session.commit()

    assert _covered(db_session, "filho_a") == {"filho_a": [PUBLIC_SITE_CODE]}
    assert _covered(db_session, "filho_x") == {}


def test_a_paused_channel_keeps_its_coverage(db_session: Session) -> None:
    _channel(db_session, enabled=False)
    _node(db_session, "fundo")
    _scope(db_session, "fundo")
    db_session.commit()

    assert _covered(db_session, "fundo") == {"fundo": [PUBLIC_SITE_CODE]}


def test_the_counts_are_one_definition_of_the_collection(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "publicado")
    _node(db_session, "semcanal")
    _node(db_session, "emrevisao", approved=False)
    _scope(db_session, "publicado")
    db_session.commit()

    counts = DiffusionPublicationRepository(db_session).counts()

    assert counts.site == 1
    assert counts.in_channels == 1
    assert counts.approved_without_channel == 1
    assert counts.in_review == 1
    assert counts.enabled_channels == 1


def test_the_lists_split_the_covered_from_the_approved_without_channel(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "publicado", title="Publicado")
    _node(db_session, "semcanal", title="Sem canal")
    _node(db_session, "emrevisao", approved=False)
    _scope(db_session, "publicado")
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
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "serie", parent_id="fundo")
    _node(db_session, "fora")
    _scope(db_session, "serie")
    db_session.commit()
    repository = DiffusionPublicationRepository(db_session)

    covered, total = repository.list_publications(state="covered", node_id="fundo")

    assert [row.description_id for row in covered] == ["serie"]
    assert total == 1


def test_the_scope_list_reports_the_origin_count_and_the_approved_count(db_session: Session) -> None:
    _channel(db_session)
    _node(db_session, "fundo")
    _node(db_session, "serie", parent_id="fundo")
    _node(db_session, "semcanal", parent_id="fundo")
    _scope(db_session, "fundo")
    db_session.commit()
    repository = DiffusionPublicationRepository(db_session)

    scopes = repository.list_scopes()

    assert len(scopes) == 1
    assert scopes[0].node_id == "fundo"
    assert scopes[0].kind == "INCLUSION"
    assert scopes[0].covered_count == 3
    assert scopes[0].approved_count == 3

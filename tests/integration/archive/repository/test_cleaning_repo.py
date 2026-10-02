import pytest
from sqlalchemy import select

from domains.archive.exceptions import CleaningRuleNotFoundError
from domains.archive.models import ArchiveCleaningRule, ArchiveDocument, ArchiveReviewStatus
from domains.archive.repository.cleaning_repo import CleaningRepository
from domains.archive.schemas.cleaning_schema import CleaningUpdateCommand
from domains.archive.services.cleaning_service import CleaningService


def _make_rule(db_session, target_column: str = "original_title") -> ArchiveCleaningRule:
    rule = ArchiveCleaningRule(
        rule_name="Troca Av por Avenida",
        target_column=target_column,
        regex_pattern=r"\bav\b\.?",
        replacement_string="Avenida",
        is_active=True,
    )
    db_session.add(rule)
    db_session.commit()
    return rule


def test_get_rule_by_id_returns_none_for_missing(use_test_db, db_session) -> None:
    """Regression: a missing rule must return None, not raise NoResultFound."""
    assert CleaningRepository(db_session).get_rule_by_id(999) is None


def test_deactivate_missing_rule_raises_domain_error(use_test_db, db_session) -> None:
    """The service must surface the domain error for a missing rule."""
    service = CleaningService(CleaningRepository(db_session))
    with pytest.raises(CleaningRuleNotFoundError, match="999"):
        service.deactivate_rule(999)


def test_get_unprocessed_documents_excludes_human_approved(use_test_db, db_session) -> None:
    """Governance: HUMAN_APPROVED documents must never be picked up by a cleaning rule."""
    rule = _make_rule(db_session)

    editable = ArchiveDocument(description_id="doc_editable", original_title="av. Brasil", staging_content_hash="h1")
    approved = ArchiveDocument(
        description_id="doc_approved",
        original_title="av. Brasil",
        staging_content_hash="h2",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )
    db_session.add_all([editable, approved])
    db_session.commit()

    repo = CleaningRepository(db_session)

    pending = repo.get_unprocessed_documents_for_rule(rule.rule_id, "original_title")
    assert [d.description_id for d in pending] == ["doc_editable"]

    sample = repo.get_random_sample_for_dry_run("original_title")
    assert "doc_approved" not in [d.description_id for d in sample]


def test_get_unprocessed_documents_skips_already_stamped(use_test_db, db_session) -> None:
    """A document already stamped with the rule key must not be returned again."""
    rule = _make_rule(db_session)

    doc = ArchiveDocument(
        description_id="doc_stamped",
        original_title="av. Brasil",
        staging_content_hash="h1",
        execution_log={f"cleaning_rule_{rule.rule_id}": "DONE"},
    )
    db_session.add(doc)
    db_session.commit()

    repo = CleaningRepository(db_session)
    assert repo.get_unprocessed_documents_for_rule(rule.rule_id, "original_title") == []


def test_deactivate_rule_success(use_test_db, db_session) -> None:
    rule = _make_rule(db_session)
    service = CleaningService(CleaningRepository(db_session))

    deactivated = service.deactivate_rule(rule.rule_id)

    assert deactivated.is_active is False
    db_session.expire_all()
    stored = db_session.execute(select(ArchiveCleaningRule).filter_by(rule_id=rule.rule_id)).scalar_one()
    assert stored.is_active is False


def test_apply_cleaning_rewrites_column_and_stamps(use_test_db, db_session) -> None:
    """The write command replaces the target column and records the rule stamp."""
    doc = ArchiveDocument(description_id="doc_clean", original_title="av. Brasil", staging_content_hash="h1")
    db_session.add(doc)
    db_session.commit()

    repo = CleaningRepository(db_session)
    repo.apply_cleaning(
        [
            CleaningUpdateCommand(
                description_id="doc_clean",
                target_column="original_title",
                new_text="Avenida Brasil",
                stamp_key="cleaning_rule_7",
            )
        ]
    )
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(ArchiveDocument, "doc_clean")
    assert stored.original_title == "Avenida Brasil"
    assert stored.execution_log == {"cleaning_rule_7": "DONE"}


def test_apply_cleaning_skips_human_approved_documents(use_test_db, db_session) -> None:
    """Race guard: a document approved after the scan must not be overwritten."""
    doc = ArchiveDocument(
        description_id="doc_locked",
        original_title="av. Brasil",
        staging_content_hash="h1",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )
    db_session.add(doc)
    db_session.commit()

    repo = CleaningRepository(db_session)
    repo.apply_cleaning(
        [
            CleaningUpdateCommand(
                description_id="doc_locked",
                target_column="original_title",
                new_text="Avenida Brasil",
                stamp_key="cleaning_rule_9",
            )
        ]
    )
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(ArchiveDocument, "doc_locked")
    assert stored.original_title == "av. Brasil"
    assert (stored.execution_log or {}) == {}

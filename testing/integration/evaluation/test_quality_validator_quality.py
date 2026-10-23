"""
Integration tests for the quality-validator bench (issue #115).

The load-bearing one is the pin: a rule the bench says fired must be a rule whose flag the worker
actually wrote into ``anomaly_reasons``, and the other way round. A bench that re-implemented the
match would score a rule the installation does not have, and the difference would only show up as a
precision nobody ever had (principle IV). The second is the ``LLM_CHECK`` floor, which the bench must
read from the worker and not carry its own copy of.
"""

from __future__ import annotations

from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository
from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO
from scrinalia.domains.archive.workers import worker_quality_validator as worker
from testing.evaluation.quality_validator_quality import (
    CLEAN,
    NO_RULE,
    all_rules,
    predict_live,
    predict_stored,
    read_candidates,
    scorable_rules,
    stored_key,
)

MATCHED = "Rua Desembargador Ermelino De Leão"
CLEAN_TITLE = "Concerto na Pedreira do Pilarzinho"


def a_validate_rule(db_session, pattern: str = r"\brua\b") -> None:
    CleaningRepository(db_session).create_rule(
        CleaningRuleCreateDTO(
            rule_name="rua abreviada",
            target_column="original_title",
            regex_pattern=pattern,
            replacement_string="",
            rule_kind="VALIDATE",
            anomaly_reason="grafia viária abreviada",
        )
    )
    db_session.flush()


def test_predict_stored_reads_exactly_the_flags_the_worker_wrote(db_session, generate_archive_doc) -> None:
    """
    The pair, measured end to end: run the real worker, then ask the bench what fired.

    The rule carries an ``anomaly_reason`` and not the rule's name, which is what makes the test
    load-bearing: a bench matching on ``rule_name`` would find nothing and report a guaranteed miss.
    """
    a_validate_rule(db_session)
    generate_archive_doc(description_id="rua1", original_title=MATCHED)
    generate_archive_doc(description_id="limpo1", original_title=CLEAN_TITLE)

    worker.execute(db=db_session, force=True)

    rules = scorable_rules(all_rules(db_session))
    predicted = predict_stored(db_session, ["rua1", "limpo1"], rules)

    assert predicted["rua1"] == {"rua abreviada"}
    assert predicted["limpo1"] == set()


def test_predict_live_agrees_with_what_the_worker_stored(db_session, generate_archive_doc) -> None:
    """Same answer down the other path: the regex evaluated now, not read from the array."""
    a_validate_rule(db_session)
    generate_archive_doc(description_id="rua1", original_title=MATCHED)
    generate_archive_doc(description_id="limpo1", original_title=CLEAN_TITLE)
    worker.execute(db=db_session, force=True)

    rules = scorable_rules(all_rules(db_session))

    assert predict_live(db_session, ["rua1", "limpo1"], rules, None, 0.6) == predict_stored(
        db_session, ["rua1", "limpo1"], rules
    )


def test_a_regex_that_does_not_match_is_not_a_flag(db_session, generate_archive_doc) -> None:
    a_validate_rule(db_session, pattern=r"\bavenida\b")
    generate_archive_doc(description_id="rua1", original_title=MATCHED)
    worker.execute(db=db_session, force=True)

    rules = scorable_rules(all_rules(db_session))

    assert predict_live(db_session, ["rua1"], rules, None, 0.6)["rua1"] == set()


def test_a_retired_rule_is_not_measured(db_session, generate_archive_doc) -> None:
    """Deactivating is how a rule stops being read, and the bench reads the active catalogue."""
    a_validate_rule(db_session)
    generate_archive_doc(description_id="rua1", original_title=MATCHED)
    rule_id = next(rule.rule_id for rule in all_rules(db_session))
    CleaningRepository(db_session).deactivate_rule(rule_id)
    db_session.flush()

    assert scorable_rules(all_rules(db_session)) == []


def test_the_candidate_strata_come_from_the_stored_flags(db_session, generate_archive_doc) -> None:
    """The picker stratifies on what the last run wrote, which is the only free ordering available."""
    a_validate_rule(db_session)
    generate_archive_doc(description_id="rua1", original_title=MATCHED)
    generate_archive_doc(description_id="limpo1", original_title=CLEAN_TITLE)
    worker.execute(db=db_session, force=True)

    rules = scorable_rules(all_rules(db_session))
    labels = {rule.anomaly_reason or rule.rule_name: rule.rule_name for rule in rules}
    candidates = {row.description_id: row.key for row in read_candidates(db_session, labels, [])}

    assert candidates["rua1"] == "rua abreviada"
    # ``limpo1`` matched no rule, but the validator flagged it for other reasons: it lands in the
    # bucket where a *miss* is looked for, which is the whole point of that stratum.
    assert candidates["limpo1"] == NO_RULE
    assert stored_key([], labels, []) == CLEAN

"""Unit tests of the structural anomaly evaluator (pure function, no database)."""

from datetime import date
from types import SimpleNamespace

from scrinalia.domains.archive.models import AnomalyReason
from scrinalia.domains.archive.schemas.ai_schemas import TitleQualityDecision
from scrinalia.domains.archive.workers.worker_quality_validator import evaluate_document

TODAY = date(2026, 10, 4)


def _doc(**overrides) -> SimpleNamespace:
    data = {
        "original_title": "Rua Izaac Ferreira da Cruz",
        "document_date": date(1954, 3, 15),
        "scope_content": "Escopo específico do documento.",
        "typology_id": 1,
        "provenance": "IPPUC",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _evaluate(doc, effective_title=None, effective_scope=None, has_tags=True, has_entities=True, **kwargs):
    return evaluate_document(
        doc=doc,
        effective_title=effective_title,
        effective_scope=effective_scope,
        has_tags=has_tags,
        has_entities=has_entities,
        repeated_titles=kwargs.pop("repeated_titles", set()),
        validate_rules=kwargs.pop("validate_rules", []),
        llm_engine=kwargs.pop("llm_engine", None),
        llm_confidence=kwargs.pop("llm_confidence", 0.6),
        today=kwargs.pop("today", TODAY),
    )


def test_a_healthy_document_has_no_reasons() -> None:
    assert _evaluate(_doc()) == []


def test_missing_date_is_reported() -> None:
    assert _evaluate(_doc(document_date=None)) == [AnomalyReason.MISSING_DATE]


def test_future_date_is_reported() -> None:
    assert _evaluate(_doc(document_date=date(2030, 1, 1))) == [AnomalyReason.FUTURE_DATE]


def test_empty_title_is_reported() -> None:
    assert AnomalyReason.EMPTY_TITLE in _evaluate(_doc(original_title="  "))
    assert AnomalyReason.EMPTY_TITLE in _evaluate(_doc(original_title="SEM TÍTULO"))
    assert AnomalyReason.EMPTY_TITLE in _evaluate(_doc(original_title="-"))


def test_an_all_caps_title_is_reported() -> None:
    assert AnomalyReason.ALL_CAPS_TITLE in _evaluate(_doc(original_title="PRACA DO BATEL EM OBRAS"))


def test_a_short_specific_title_is_not_all_caps() -> None:
    assert AnomalyReason.ALL_CAPS_TITLE not in _evaluate(_doc(original_title="BATEL"))


def test_a_repeated_title_is_reported() -> None:
    reasons = _evaluate(_doc(original_title="Registros Fotográficos"), repeated_titles={"registros fotográficos"})
    assert AnomalyReason.REPEATED_TITLE in reasons


def test_a_title_that_is_only_the_fixed_template_is_reported() -> None:
    """The approved title template removed everything: the specific part is missing."""
    reasons = _evaluate(_doc(original_title="Registros Fotográficos -"), effective_title="")
    assert AnomalyReason.TITLE_ONLY_TEMPLATE in reasons


def test_a_scope_covered_by_boilerplate_is_reported() -> None:
    reasons = _evaluate(_doc(scope_content="Acervo de 35.327 fotografias"), effective_scope="")
    assert AnomalyReason.SCOPE_ONLY_BOILERPLATE in reasons


def test_an_absent_scope_is_not_a_boilerplate_anomaly() -> None:
    assert AnomalyReason.SCOPE_ONLY_BOILERPLATE not in _evaluate(_doc(scope_content=None), effective_scope=None)


def test_pipeline_gaps_are_reported() -> None:
    assert _evaluate(_doc(), has_tags=False) == [AnomalyReason.NO_TAGS]
    assert _evaluate(_doc(), has_entities=False) == [AnomalyReason.NO_ENTITIES]
    assert _evaluate(_doc(typology_id=None)) == [AnomalyReason.NO_TYPOLOGY]


def test_a_registered_validate_rule_is_applied() -> None:
    import re

    from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleDTO

    rule = CleaningRuleDTO(
        rule_id=7,
        rule_name="Título com código",
        target_column="original_title",
        regex_pattern=r"\b\d{4}-\d{2}\b",
        replacement_string="",
        rule_kind="VALIDATE",
        anomaly_reason="Título com código de controle",
        is_active=True,
    )

    reasons = _evaluate(
        _doc(original_title="Obras 2023-07 na Rua X"), validate_rules=[(rule, re.compile(rule.regex_pattern))]
    )

    assert reasons == [f"{AnomalyReason.RULE_MATCH}:Título com código de controle"]


def test_a_rule_reason_falls_back_to_the_rule_name() -> None:
    import re

    from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleDTO

    rule = CleaningRuleDTO(
        rule_id=8,
        rule_name="Sem motivo cadastrado",
        target_column="scope_content",
        regex_pattern="x{3}",
        replacement_string="",
        rule_kind="VALIDATE",
        is_active=True,
    )

    reasons = _evaluate(_doc(scope_content="xxx"), validate_rules=[(rule, re.compile(rule.regex_pattern))])
    assert reasons == [f"{AnomalyReason.RULE_MATCH}:Sem motivo cadastrado"]


class _FakeLlm:
    def __init__(self, decision: TitleQualityDecision) -> None:
        self.decision = decision
        self.calls = 0

    def check_title(self, title: str) -> TitleQualityDecision:
        self.calls += 1
        return self.decision


def test_the_llm_only_flags_above_the_confidence_floor() -> None:
    engine = _FakeLlm(TitleQualityDecision(is_suspect=True, confidence=0.4, reason="talvez"))
    assert _evaluate(_doc(), llm_engine=engine) == []
    assert engine.calls == 1

    confident = _FakeLlm(TitleQualityDecision(is_suspect=True, confidence=0.9, reason="palavra truncada"))
    reasons = _evaluate(_doc(), llm_engine=confident)
    assert reasons == [f"{AnomalyReason.LLM_SUSPECT}:palavra truncada"]


def test_the_llm_is_never_called_without_a_rule() -> None:
    """The default is deterministic: no engine means no model cost."""
    engine = _FakeLlm(TitleQualityDecision(is_suspect=True, confidence=0.99, reason="x"))
    _evaluate(_doc(), llm_engine=None)
    assert engine.calls == 0


def test_a_document_accumulates_every_reason_in_a_stable_order() -> None:
    reasons = _evaluate(
        _doc(document_date=None, original_title="", typology_id=None),
        has_tags=False,
        has_entities=False,
        effective_scope="",
    )

    assert reasons == [
        AnomalyReason.MISSING_DATE,
        AnomalyReason.EMPTY_TITLE,
        AnomalyReason.SCOPE_ONLY_BOILERPLATE,
        AnomalyReason.NO_TAGS,
        AnomalyReason.NO_TYPOLOGY,
        AnomalyReason.NO_ENTITIES,
    ]

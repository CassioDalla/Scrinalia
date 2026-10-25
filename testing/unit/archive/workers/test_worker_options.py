"""What a worker accepts: its signature, and the one door it names (#120).

The issue is about a declaration that nothing read: ``validate_options`` checked the key's *name*
against the signature and stopped there, ``**engine_kwargs`` made any key legal, and the panel could
not say what a worker took. These tests pin the three halves of the fix:

* the options are **derived** from ``execute`` — name, kind, default and the catalogue a column list
  is checked against — so the contract cannot offer a key the write path refuses;
* a value is checked against its declared type, and a column against
  :data:`AI_TEXT_COLUMNS` — the same tuple the evaluation benches read;
* the raw engine pass-through is a **separate, named** door (``engine_options``), so
  ``{"colunas_to_classify": ...}`` is refused instead of reaching a constructor as a ``TypeError``.
"""

from inspect import Parameter
from typing import Any

import pytest

from scrinalia.domains.archive.domain.text_quality import AI_TEXT_COLUMNS
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError
from scrinalia.domains.archive.models.operations import WorkerSetting
from scrinalia.domains.archive.workers import catalogue
from scrinalia.domains.archive.workers.configuration import (
    COLUMN_OPTIONS,
    NON_OPTION_PARAMETERS,
    RUN_ONLY_OPTIONS,
    SEPARATE_OPTIONS,
    declared_options,
    effective_worker_options,
    resolve_configuration,
    validate_engine_options,
    validate_options,
    validate_settings_options,
)

ALL_SPECS = list(catalogue.WORKER_CATALOGUE.values())
WORKERS_WITH_OPTIONS = [spec for spec in ALL_SPECS if declared_options(spec)]


def _spec(name: str) -> catalogue.WorkerSpec:
    return catalogue.WORKER_CATALOGUE[name]


def _names(spec: catalogue.WorkerSpec) -> set[str]:
    return {option.name for option in declared_options(spec)}


# --- the declaration ---------------------------------------------------------------------------


def test_the_columns_options_are_checked_against_the_one_ai_text_list() -> None:
    """One list, two readers: the write path and the benches both read ``AI_TEXT_COLUMNS``."""
    assert COLUMN_OPTIONS["columns_to_extract"] is AI_TEXT_COLUMNS
    assert COLUMN_OPTIONS["columns_to_classify"] is AI_TEXT_COLUMNS

    extract = next(option for option in declared_options(_spec("ner")) if option.name == "columns_to_extract")
    classify = next(option for option in declared_options(_spec("typology")) if option.name == "columns_to_classify")
    assert extract.kind == classify.kind == "columns"
    assert extract.choices == classify.choices == AI_TEXT_COLUMNS


def test_every_list_option_has_a_declared_source() -> None:
    """
    A new list-typed option cannot skip validation by not being in ``COLUMN_OPTIONS``.

    The gate: the vocabulary the panel offers and the list the write path checks are the same, so an
    option that carries column names has to say which catalogue those names come from.
    """
    unlisted: list[str] = []
    for spec in ALL_SPECS:
        for name in _declared_parameters(spec):
            if name in NON_OPTION_PARAMETERS or name in SEPARATE_OPTIONS:
                continue
            if _annotation_is_list(spec, name) and name not in COLUMN_OPTIONS:
                unlisted.append(f"{spec.name}.{name}")
    assert not unlisted, (
        f"these options take a list but not a catalogue: {unlisted}. "
        "Declare them in `COLUMN_OPTIONS` (and in the panel's choices) or they cannot be validated."
    )


def test_the_run_cap_is_the_only_run_only_option() -> None:
    assert {"limit"} == RUN_ONLY_OPTIONS
    limit = next(option for option in declared_options(_spec("ner")) if option.name == "limit")
    assert limit.scope == "run"
    force = next(option for option in declared_options(_spec("ner")) if option.name == "force")
    assert force.scope == "both"


def test_a_worker_without_engine_kwargs_declares_no_free_key() -> None:
    assert catalogue.engine_option_names(_spec("thumbnail")) == ()
    assert catalogue.engine_option_names(_spec("transfer")) == ()


def test_the_engine_pass_through_comes_from_the_axis_presets() -> None:
    """
    The names are derived, never invented: the axis already hands these to the engine constructor.

    ``disable`` and ``batch_size`` are preset keys; ``host`` is what the two Ollama axes inject in
    ``describe_config`` instead of putting it in a preset.
    """
    assert set(catalogue.engine_option_names(_spec("ner"))) == {"model", "device", "disable"}
    assert set(catalogue.engine_option_names(_spec("embedding"))) == {
        "model",
        "device",
        "batch_size",
        "dimensions",
    }
    # The quality validator takes its engine from the LLM_CHECK rule and still has the door.
    assert set(catalogue.engine_option_names(_spec("quality-validator"))) == {"model", "host"}
    # The conflict judge declares engine/preset but no ``**kwargs``: it has nothing to pass through.
    assert set(catalogue.engine_option_names(_spec("conflict-judge"))) == set()


def test_every_option_resolver_is_a_function_of_the_worker_module() -> None:
    resolving = [spec for spec in ALL_SPECS if spec.option_resolver is not None]
    assert {spec.name for spec in resolving} == {"ner", "typology", "macro-category"}
    for spec in resolving:
        assert callable(getattr(catalogue.worker_module(spec.module), spec.option_resolver or ""))


# --- a name that is not an option --------------------------------------------------------------


def test_a_column_typo_is_refused_and_the_sentence_names_the_known_columns() -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="admin_bio_historia") as refused:
        validate_options(_spec("typology"), {"columns_to_classify": ["original_title", "admin_bio_historia"]})

    assert "scope_content" in str(refused.value)
    assert "Conhecidas" in str(refused.value)


def test_an_empty_column_list_is_refused() -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="vazia"):
        validate_options(_spec("ner"), {"columns_to_extract": []})


def test_an_unknown_key_is_refused_even_where_the_worker_ends_in_engine_kwargs() -> None:
    """The measured defect: ``{"colunas_to_classify": [...]}`` was stored as a default."""
    with pytest.raises(InvalidWorkerSettingsError, match="não aceita a opção 'colunas_to_classify'") as refused:
        validate_options(_spec("typology"), {"colunas_to_classify": ["original_title"]})

    assert "--engine-option" in str(refused.value)


def test_a_worker_without_the_engine_door_has_no_pass_through_sentence() -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="não aceita a opção 'device'") as refused:
        validate_options(_spec("thumbnail"), {"device": "cpu"})

    assert "--engine-option" not in str(refused.value)


@pytest.mark.parametrize("key", ["config", "source", "storage", "db", "db_session"])
def test_an_infrastructure_parameter_is_not_an_option(key: str) -> None:
    spec = _spec("transfer") if key in {"source", "db_session"} else _spec("thumbnail")
    with pytest.raises(InvalidWorkerSettingsError):
        validate_options(spec, {key: "x"})


@pytest.mark.parametrize("key", sorted(SEPARATE_OPTIONS))
def test_a_field_of_its_own_is_not_set_through_options(key: str) -> None:
    """``extra`` is applied after the resolved argument: two definitions of the same field."""
    with pytest.raises(InvalidWorkerSettingsError, match="campo próprio"):
        validate_options(_spec("ner"), {key: "x"})


# --- a value the option cannot carry -----------------------------------------------------------


@pytest.mark.parametrize(
    ("spec_name", "option", "value"),
    [
        ("ner", "force", "false"),
        ("ner", "limit", "10"),
        ("typology", "confidence_threshold", "alto"),
        ("thumbnail", "storage", 42),
        ("ner", "columns_to_extract", "original_title"),
        ("ner", "columns_to_extract", ["original_title", 7]),
    ],
)
def test_a_value_of_the_wrong_type_is_refused(spec_name: str, option: str, value: Any) -> None:
    with pytest.raises(InvalidWorkerSettingsError):
        validate_options(_spec(spec_name), {option: value})


def test_a_valid_configuration_passes() -> None:
    validate_options(
        _spec("typology"),
        {"columns_to_classify": ["original_title", "scope_content"], "confidence_threshold": 0.9, "force": True},
    )


def test_a_persisted_default_cannot_carry_a_run_cap() -> None:
    """A cap that outlived the command would stop every run at N units."""
    with pytest.raises(InvalidWorkerSettingsError, match="execução"):
        validate_settings_options(_spec("ner"), {"limit": 10})
    # ``force`` is a deliberate default: the way back from a mark a transient outage left behind.
    validate_settings_options(_spec("thumbnail"), {"force": True})


# --- the named exception ------------------------------------------------------------------------


def test_a_declared_option_is_not_a_pass_through() -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="use 'options'"):
        validate_engine_options(_spec("ner"), {"force": True})


def test_a_worker_without_engine_kwargs_has_no_pass_through() -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="não repassa"):
        validate_engine_options(_spec("thumbnail"), {"device": "cpu"})


def test_the_pass_through_accepts_a_library_key_the_axis_never_named() -> None:
    """The keys are deliberately not enumerated: the engine is the one that validates the value."""
    validate_engine_options(_spec("ner"), {"max_length": 256})


# --- resolution and the effective values --------------------------------------------------------


def test_a_stale_persisted_option_is_ignored_with_a_note() -> None:
    """
    The read survives what the write refuses (#122's lesson): an old row keeps the panel up.

    The typo is not promoted to an engine pass-through either — it is dropped, and the row is healed
    the next time somebody saves the screen.
    """
    setting = WorkerSetting(worker_name="ner", options={"colunas_to_classify": ["original_title"]})

    resolved = resolve_configuration(None, _spec("ner"), setting)  # type: ignore[arg-type]

    assert resolved.worker_options == {}
    assert resolved.note is not None
    assert "colunas_to_classify" in resolved.note


def test_a_persisted_run_cap_is_ignored_with_a_note() -> None:
    setting = WorkerSetting(worker_name="ner", options={"limit": 10})

    resolved = resolve_configuration(None, _spec("ner"), setting)  # type: ignore[arg-type]

    assert resolved.worker_options == {}
    assert resolved.note is not None and "limit" in resolved.note


def test_a_pass_through_travels_as_engine_kwargs_and_reaches_the_config() -> None:
    resolved = resolve_configuration(None, _spec("ner"), engine_options={"device": "cpu"})  # type: ignore[arg-type]

    assert resolved.worker_options == {}
    assert resolved.engine_kwargs == {"device": "cpu"}
    assert resolved.config["device"] == "cpu"


def test_the_effective_options_fill_the_columns_the_signature_cannot() -> None:
    """
    "Which columns did run #N read?" has an answer even when nobody named them.

    ``columns_to_extract`` defaults to ``None`` in the signature; the worker resolves the code
    default from ``NerRunnerConfig``. The ledger records that resolution, not the ``None``.
    """
    resolved = resolve_configuration(None, _spec("ner"))  # type: ignore[arg-type]

    assert effective_worker_options(_spec("ner"), resolved)["columns_to_extract"] == [
        "original_title",
        "admin_bio_history",
        "provenance",
        "scope_content",
    ]


def test_the_effective_options_record_the_named_value_and_the_floor() -> None:
    resolved = resolve_configuration(
        None,  # type: ignore[arg-type]
        _spec("typology"),
        options={"columns_to_classify": ["scope_content"]},
    )

    effective = effective_worker_options(_spec("typology"), resolved)
    assert effective["columns_to_classify"] == ["scope_content"]
    # The floor defaults to the runner config (0.40), not to the ``None`` of the signature.
    assert effective["confidence_threshold"] == 0.40


# --- helpers ------------------------------------------------------------------------------------


def _declared_parameters(spec: catalogue.WorkerSpec) -> dict[str, Parameter]:
    from scrinalia.domains.archive.workers.configuration import declared_parameters

    return declared_parameters(spec)


def _annotation_is_list(spec: catalogue.WorkerSpec, name: str) -> bool:
    """Whether the option's annotation mentions ``list``, resolved from ``__future__`` strings."""
    from typing import get_args, get_origin, get_type_hints

    annotation = get_type_hints(catalogue.worker_function(spec)).get(name)
    if get_origin(annotation) is list:
        return True
    return any(get_origin(member) is list for member in get_args(annotation))

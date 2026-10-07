"""The worker catalogue is the single definition the panel and the runner share.

These tests are the guard against the panel lying: a worker added to the runner without a spec, a
default engine/preset that does not exist in the axis registry, or a counter whose signature would
blow up when the operations service passes the effective options.
"""

import inspect

import pytest

from scrinalia.domains.archive.workers import catalogue, runner

SIGNATURE_DRIVEN = [spec for spec in catalogue.WORKER_CATALOGUE.values() if spec.engine_source == "signature"]
ALL_SPECS = list(catalogue.WORKER_CATALOGUE.values())


def test_every_runner_worker_has_a_spec_and_the_order_is_the_pipeline() -> None:
    assert set(catalogue.WORKER_CATALOGUE) == set(runner.WORKERS)
    assert list(catalogue.WORKER_CATALOGUE) == runner.PIPELINE_ORDER


def test_every_spec_has_a_module_that_exposes_execute() -> None:
    for spec in ALL_SPECS:
        assert inspect.isfunction(catalogue.worker_function(spec))
        assert isinstance(catalogue.worker_signature(spec), inspect.Signature)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda spec: spec.name)
def test_counters_accept_the_effective_options(spec) -> None:
    """The service forwards the persisted options, so a counter must tolerate unknown keywords."""
    if spec.counter is not None:
        parameters = inspect.signature(getattr(catalogue.worker_module(spec.module), spec.counter)).parameters
        assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    if spec.processed_counter is not None:
        parameters = inspect.signature(getattr(catalogue.worker_module(spec.module), spec.processed_counter)).parameters
        assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    if spec.failed_counter is not None:
        parameters = inspect.signature(getattr(catalogue.worker_module(spec.module), spec.failed_counter)).parameters
        assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())


@pytest.mark.parametrize("spec", SIGNATURE_DRIVEN, ids=lambda spec: spec.name)
def test_signature_driven_defaults_exist_in_the_axis_registry(spec) -> None:
    """
    The engine/preset a worker declares in its signature must be real.

    A renamed preset would otherwise surface as a 500 on the panel instead of a failing test.
    """
    parameters = catalogue.worker_signature(spec).parameters
    assert "engine_name" in parameters and "preset" in parameters

    registry = catalogue.axis_registry(spec.axis)
    engine_name = parameters["engine_name"].default
    preset = parameters["preset"].default

    assert engine_name in registry.AVAILABLE_ENGINES
    assert preset in registry.PRESETS
    described = registry.describe_config(engine_name, preset=preset)
    assert described, f"{spec.name} described an empty configuration"


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda spec: spec.name)
def test_axis_points_at_a_known_registry(spec) -> None:
    if spec.axis is None:
        return
    assert spec.axis in catalogue.ENGINE_AXES


def test_only_the_signature_driven_workers_expose_an_engine_parameter() -> None:
    """The quality validator's engine lives in the LLM_CHECK rule, not in its signature."""
    for spec in ALL_SPECS:
        parameters = catalogue.worker_signature(spec).parameters
        if spec.engine_source == "signature":
            assert "engine_name" in parameters
        else:
            assert "engine_name" not in parameters


def test_the_unmeasurable_worker_says_why() -> None:
    conflict = catalogue.WORKER_CATALOGUE["conflict-judge"]
    assert conflict.counter is None
    assert conflict.unmeasurable_reason
    assert conflict.processed_counter == "count_judged"
    with pytest.raises(ValueError, match="no measurable queue"):
        catalogue.count_pending(conflict, db=None)  # type: ignore[arg-type]


def test_the_thumbnail_worker_uses_the_storage_uri_not_a_stamp() -> None:
    """The thumbnail's ledger is the URI in the bucket, which is why it names explicit counters."""
    thumbnail = catalogue.WORKER_CATALOGUE["thumbnail"]
    assert thumbnail.stamp is None
    assert thumbnail.processed_counter == "count_processed"
    assert thumbnail.failed_counter == "count_failed"


def test_governance_flags_match_the_documented_exceptions() -> None:
    """The two documented exceptions must stay visible in the panel."""
    assert catalogue.WORKER_CATALOGUE["embedding"].governed is False
    assert catalogue.WORKER_CATALOGUE["macro-category"].governed is False
    assert catalogue.WORKER_CATALOGUE["ner"].governed is True

"""
Unit tests for the subject bench's model seam (issue #116).

The bench used to carry its own model catalogue: two adapters that built ``transformers`` pipelines
and a ``MODELS`` dictionary inside the script, so a third model was a code edit. These tests pin the
replacement. The models come from ``engines.classification.registry`` — the same registry both
workers of the axis read — so a new model is a registry entry and this script never names one.
"""

from __future__ import annotations

import inspect

import pytest

from scrinalia.domains.archive.engines.classification import registry as classification_registry
from scrinalia.domains.archive.workers.worker_macro_category import execute
from testing.evaluation.macro_category_quality import (
    BenchConfig,
    engine_classifier,
    parse_config,
    worker_default_config,
)


def test_parse_config_reads_the_engine_and_the_preset() -> None:
    config = parse_config("deberta_typology:cpu_local", device="cuda:0")

    assert (config.engine, config.preset) == ("deberta_typology", "cpu_local")
    assert config.label == "deberta_typology:cpu_local"
    assert config.engine_kwargs == {"device": "cuda:0"}
    # The model is resolved through the registry; the test types no model name on purpose.
    assert config.model == classification_registry.PRESETS["cpu_local"]["model"]


def test_the_default_configuration_is_the_workers_own() -> None:
    """Retyping the worker's default here would let the bench measure a model the run never uses."""
    parameters = inspect.signature(execute).parameters

    assert worker_default_config() == f"{parameters['engine_name'].default}:{parameters['preset'].default}"


def test_an_unknown_engine_or_preset_is_refused_with_the_registry_options() -> None:
    with pytest.raises(SystemExit, match="names an engine the axis does not have"):
        parse_config("motor_inexistente")
    with pytest.raises(SystemExit, match="names a preset the axis does not have"):
        parse_config("deberta_typology:preset_inexistente")
    with pytest.raises(SystemExit, match="expected engine"):
        parse_config("deberta_typology:cpu_local:extra")


def test_a_new_registry_entry_is_a_new_configuration(monkeypatch) -> None:
    """
    The pin: the registry is the only source of models.

    A model that exists only there becomes runnable without editing the bench — which is what "a new
    model is a registry entry" means, and what the two hardcoded adapters could not do.
    """
    monkeypatch.setitem(classification_registry.AVAILABLE_ENGINES, "motor_novo", object)
    monkeypatch.setitem(classification_registry.PRESETS, "preset_novo", {"model": "modelo-novo", "device": "cpu"})

    config = parse_config("motor_novo:preset_novo")

    assert config.label == "motor_novo:preset_novo"
    assert config.model == "modelo-novo"


def test_the_bench_builds_its_engine_through_the_registry(monkeypatch) -> None:
    """The engine is the axis's own object, and the device override is the only thing the bench adds."""
    calls: list[tuple[str, str | None, dict]] = []

    class FakeEngine:
        def classify(self, texts: list[str], labels: list[str], **kwargs) -> list[dict]:
            return [{"labels": [labels[0]], "scores": [0.5]}]

    def fake_get_engine(engine_name, preset=None, **kwargs):
        calls.append((engine_name, preset, kwargs))
        return FakeEngine()

    monkeypatch.setattr(classification_registry, "get_engine", fake_get_engine)

    classify = engine_classifier(BenchConfig(engine="deberta_typology", preset="cpu_local", device="cuda:0"))

    assert classify("igrejas", ["Religião"]) == {"label": "Religião", "score": 0.5}
    assert calls == [("deberta_typology", "cpu_local", {"device": "cuda:0"})]

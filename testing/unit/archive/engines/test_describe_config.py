"""``describe_config`` is the read-only twin of ``get_engine``.

The operational panel answers "with which preset and which model will this worker run?" for a
worker that may never have run, so it cannot pay for loading spaCy, torch or transformers. These
tests pin the two halves together: the configuration the factory *forwards* and the configuration
the registry *describes* must be the same dictionary, and describing must instantiate nothing.
"""

import pytest

from scrinalia.core import config as core_config
from scrinalia.domains.archive.engines.classification import registry as classification_registry
from scrinalia.domains.archive.engines.embeddings import registry as embeddings_registry
from scrinalia.domains.archive.engines.LLMs import registry as llm_registry
from scrinalia.domains.archive.engines.NER import registry as ner_registry
from scrinalia.domains.archive.engines.title_quality import registry as title_registry

#: ``(registry, engine, preset)`` for every axis a worker actually runs on. Clustering is absent on
#: purpose: no worker in the runner uses it, and its factory injects a callable analyzer that has no
#: honest representation in a serialisable config.
AXES = [
    (ner_registry, "spacy_ner", "gpu"),
    (classification_registry, "deberta_typology", "cpu_local"),
    (embeddings_registry, "sentence_transformer", "multilingual_minilm"),
    (llm_registry, "ollama_judge", "granite_local"),
    (title_registry, "ollama_title_check", "granite_local"),
]


@pytest.fixture
def capture(monkeypatch):
    """Replaces the engine class of one registry and returns the list of captured kwargs."""

    def _install(registry_module, engine_name):
        instances: list[dict] = []

        class Capture:
            """Stand-in for a real engine: records the kwargs the factory forwarded."""

            def __init__(self, **kwargs) -> None:
                instances.append(kwargs)

        monkeypatch.setitem(registry_module.AVAILABLE_ENGINES, engine_name, Capture)
        return instances

    return _install


@pytest.mark.parametrize(("registry_module", "engine_name", "preset"), AXES)
def test_describe_config_matches_what_get_engine_forwards(capture, registry_module, engine_name, preset) -> None:
    instances = capture(registry_module, engine_name)

    registry_module.get_engine(engine_name, preset=preset)
    assert len(instances) == 1
    forwarded = instances[0]

    described = registry_module.describe_config(engine_name, preset=preset)

    assert described == forwarded
    # Describing must not build a second engine.
    assert len(instances) == 1


@pytest.mark.parametrize(("registry_module", "engine_name", "preset"), AXES)
def test_describe_config_honours_manual_overrides(capture, registry_module, engine_name, preset) -> None:
    instances = capture(registry_module, engine_name)

    registry_module.get_engine(engine_name, preset=preset, device="cuda:0")
    described = registry_module.describe_config(engine_name, preset=preset, device="cuda:0")

    assert described["device"] == "cuda:0"
    assert described == instances[0]


@pytest.mark.parametrize(("registry_module", "engine_name", "preset"), AXES)
def test_describe_config_rejects_unknown_engine_and_preset(registry_module, engine_name, preset) -> None:
    with pytest.raises(ValueError, match="não suportado"):
        registry_module.describe_config("motor_inexistente")

    with pytest.raises(ValueError, match="não encontrado"):
        registry_module.describe_config(engine_name, preset="preset_fantasma")


def test_llm_host_comes_from_the_environment(monkeypatch) -> None:
    """
    ``OLLAMA_HOST_URL`` has to reach every preset-backed engine.

    The host used to be hardcoded in ``PRESETS``, so the environment variable only reached the
    generic ``OllamaClient`` and every engine built through a preset called localhost regardless.
    """
    monkeypatch.setattr(core_config.settings, "OLLAMA_HOST_URL", "http://ollama.interno:11434")

    assert core_config.resolve_ollama_host() == "http://ollama.interno:11434"

    for registry_module, engine_name in (
        (llm_registry, "ollama_judge"),
        (title_registry, "ollama_title_check"),
    ):
        assert (
            registry_module.describe_config(engine_name, preset="granite_local")["host"]
            == "http://ollama.interno:11434"
        )

    engine = llm_registry.get_engine("ollama_judge", preset="granite_local")
    assert engine.host == "http://ollama.interno:11434/api/generate"


def test_an_explicit_host_still_beats_the_environment(monkeypatch) -> None:
    """A per-run ``--option host=...`` is the caller's final say, exactly like any other kwarg."""
    monkeypatch.setattr(core_config.settings, "OLLAMA_HOST_URL", "http://ollama.interno:11434")

    assert core_config.resolve_ollama_host("http://outro:11434") == "http://outro:11434"
    assert (
        llm_registry.describe_config("ollama_judge", preset="granite_local", host="http://outro:11434")["host"]
        == "http://outro:11434"
    )


def test_the_default_host_is_used_when_nothing_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(core_config.settings, "OLLAMA_HOST_URL", None)

    assert core_config.resolve_ollama_host() == core_config.DEFAULT_OLLAMA_HOST
    assert (
        llm_registry.describe_config("ollama_judge", preset="gemma_4b_local")["host"] == core_config.DEFAULT_OLLAMA_HOST
    )

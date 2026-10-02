import pytest

from domains.archive.engines.classification import registry as typology_registry
from domains.archive.engines.clustering import registry as cluster_registry
from domains.archive.engines.NER import registry as ner_registry

# Put them all in a list
ALL_REGISTRIES = [typology_registry, ner_registry, cluster_registry]


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_rejects_invalid_engine(mock_registry, reg_module):
    mock_registry(reg_module)

    with pytest.raises(ValueError, match="não suportado"):
        reg_module.get_engine("inexistente")


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_kwargs_override_preset(mock_registry, reg_module):
    # Store the fake class returned by the factory
    mock_engine_class = mock_registry(reg_module)

    # We request preset_teste (which has device="cpu"), BUT force device="cuda:0"
    reg_module.get_engine("motor_fake", preset="preset_teste", device="cuda:0")

    # The golden rule: "cuda:0" must have crushed "cpu"
    mock_engine_class.assert_called_once_with(model="falso", device="cuda:0")


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_rejects_invalid_preset(mock_registry, reg_module):
    # 1. Trigger the Fixture Factory for the current registry
    mock_registry(reg_module)

    # 2. Try to trigger the factory with the ghost preset
    with pytest.raises(ValueError, match="não encontrado"):
        reg_module.get_engine("motor_fake", preset="preset_fantasma")


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_loads_preset_correctly(mock_registry, reg_module):
    # 1. Mock the registry for the current round
    mock_engine_class = mock_registry(reg_module)

    # 2. Run the real factory
    reg_module.get_engine("motor_fake", preset="preset_teste")

    # 3. Check that the factory forwarded the right data
    mock_engine_class.assert_called_once_with(model="falso", device="cpu")

import pytest

# Importa todos os Registry
from domains.archive.engines.classification import registry as typology_registry
from domains.archive.engines.NER import registry as ner_registry

# Coloque todos numa lista
ALL_REGISTRIES = [
    typology_registry,
    ner_registry,
]


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_rejeita_motor_invalido(mock_registry, reg_module):
    mock_engine_class = mock_registry(reg_module)

    with pytest.raises(ValueError, match="não suportado"):
        reg_module.get_engine("inexistente")


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_kwargs_sobrescrevem_preset(mock_registry, reg_module):
    # Armazenamos a classe falsa retornada pela fábrica
    mock_engine_class = mock_registry(reg_module)

    # Pedimos o preset_teste (que tem device="cpu"), MAS forçamos device="cuda:0"
    engine = reg_module.get_engine("motor_fake", preset="preset_teste", device="cuda:0")

    # A regra de ouro: o "cuda:0" deve ter esmagado o "cpu"
    mock_engine_class.assert_called_once_with(model="falso", device="cuda:0")


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_rejeita_preset_invalido(mock_registry, reg_module):
    # 1. Aciona a Fixture Factory para o registry da rodada atual
    mock_registry(reg_module)

    # 2. Tenta acionar a fábrica com o preset fantasma
    with pytest.raises(ValueError, match="não encontrado"):
        reg_module.get_engine("motor_fake", preset="preset_fantasma")


@pytest.mark.parametrize("reg_module", ALL_REGISTRIES)
def test_get_engine_carrega_preset_corretamente(mock_registry, reg_module):
    # 1. Mocka o registry da rodada
    mock_engine_class = mock_registry(reg_module)

    # 2. Executa a fábrica real
    engine = reg_module.get_engine("motor_fake", preset="preset_teste")

    # 3. Verifica se a fábrica repassou os dados certos
    mock_engine_class.assert_called_once_with(model="falso", device="cpu")

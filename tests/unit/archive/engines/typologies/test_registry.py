import pytest

from domains.archive.engines.typologies import registry


def test_get_engine_rejeita_motor_invalido():
    # Este teste não precisa da fixture, pois já testa a rejeição nativa
    with pytest.raises(ValueError, match="não suportado"):
        registry.get_engine("motor_inexistente")  # type: ignore


def test_get_engine_rejeita_preset_invalido(mock_registry_typology):
    # Passamos um motor válido (o nosso fake), mas um preset que não existe
    with pytest.raises(ValueError, match="não encontrado"):
        registry.get_engine("motor_fake", preset="preset_fantasma")  # type: ignore


def test_get_engine_carrega_preset_corretamente(mock_registry_typology):
    # Executa a fábrica chamando o motor e preset injetados pela fixture
    engine = registry.get_engine("motor_fake", preset="preset_teste")  # type: ignore

    # A fábrica chamou a classe passando os hiperparâmetros corretos do preset?
    mock_registry_typology.assert_called_once_with(model="modelo_falso_v1", device="cpu")


def test_get_engine_kwargs_sobrescrevem_preset(mock_registry_typology):
    # O utilizador pede o preset_teste, mas força o device para cuda:0
    engine = registry.get_engine("motor_fake", preset="preset_teste", device="cuda:0")  # type: ignore

    # A regra de ouro funcionou? O dicionário kwargs esmagou o preset?
    mock_registry_typology.assert_called_once_with(model="modelo_falso_v1", device="cuda:0")

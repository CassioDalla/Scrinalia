from unittest.mock import MagicMock, patch

from domains.archive.engines.classification import registry
from domains.archive.workers.worker_typology import execute

# ==========================================
# 1. TESTE UNITÁRIO (Foco na Lógica Python)
# ==========================================


class MockArchiveDocument:
    """Dublê super leve apenas para o teste unitário."""

    def __init__(self, id, title, content):
        self.description_id = id
        self.original_title = title
        self.scope_content = content
        self.typology_id = None
        self.execution_log = None


@patch("domains.archive.workers.worker_typology.repository.get_active_typologies")
def test_worker_unitario_logica_de_concatenacao(
    mock_get_typologies,
    mock_registry,
):
    # 1. Prepara o Banco Falso
    mock_session = MagicMock()
    mock_get_typologies.return_value = {"Contrato": 1}

    doc_teste = MockArchiveDocument(1, "Contrato de Prestação de Serviços", None)
    mock_session.scalars.return_value.all.side_effect = [[doc_teste], []]

    # 2. Prepara a IA Falsa (Acessando a instância gerada pela nossa Fábrica mockada)
    # mock_registry_typology é a CLASSE. O .return_value pega a INSTÂNCIA.

    MockClass = mock_registry(registry)
    instancia_da_ia = MockClass.return_value
    instancia_da_ia.classify.return_value = [{"labels": ["Contrato"], "scores": [0.95]}]

    # 3. Ação: Passamos o nome do motor falso que a fixture injetou no registry!
    execute(
        db=mock_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )  # type: ignore

    # 4. Verificações (Asserts)
    # Validamos se a concatenação de colunas funcionou (ignorou o scope_content nulo)
    instancia_da_ia.classify.assert_called_once()
    args, _ = instancia_da_ia.classify.call_args
    assert args[0] == ["Contrato de Prestação de Serviços"]

    assert doc_teste.typology_id == 1
    assert doc_teste.execution_log["worker_typology_classifier_v1"] == "DONE"  # type: ignore
    mock_session.commit.assert_called_once()

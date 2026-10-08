"""HTTP contract of the cleaning-rules controller."""

from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)
from litestar.testing import TestClient

from scrinalia.domains.archive.exceptions import CleaningRuleNotFoundError, InvalidParam
from scrinalia.domains.archive.schemas.cleaning_schema import (
    CleaningRuleDTO,
    DryRunMatchDTO,
    DryRunResponseDTO,
)
from scrinalia.domains.archive.services.cleaning_service import CleaningService


def _rule(rule_id: int = 1) -> CleaningRuleDTO:
    return CleaningRuleDTO(
        rule_id=rule_id,
        rule_name="Troca Av por Avenida",
        target_column="original_title",
        regex_pattern=r"\bav\b\.?",
        replacement_string="Avenida",
        created_by=None,
        is_active=True,
    )


# ==========================================
# 1. LISTING
# ==========================================


def test_list_rules_serialises_the_dtos(client: TestClient, mocker):
    mock_list = mocker.patch.object(CleaningService, "list_rules")
    mock_list.return_value = [_rule(1), _rule(2)]

    response = client.get("/api/v1/quality/cleaning-rules/")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert [rule["rule_id"] for rule in body] == [1, 2]
    assert body[0]["regex_pattern"] == r"\bav\b\.?"
    # The default is the workers' view: only what is active.
    mock_list.assert_called_once_with(include_inactive=False)


def test_list_rules_can_include_the_retired_ones(client: TestClient, mocker):
    """The way back needs to see what was retired; nothing here deletes a rule."""
    mock_list = mocker.patch.object(CleaningService, "list_rules")
    retired = _rule(7)
    retired.is_active = False
    mock_list.return_value = [retired]

    response = client.get("/api/v1/quality/cleaning-rules/?include_inactive=true")

    assert response.status_code == HTTP_200_OK
    assert response.json()[0]["is_active"] is False
    mock_list.assert_called_once_with(include_inactive=True)


# ==========================================
# 2. CREATION (CONTROLLER AS TRANSLATOR)
# ==========================================


def test_create_rule_translates_the_request_into_a_dto(client: TestClient, mocker):
    """The controller maps HTTP into the domain DTO instead of passing the request through."""
    mock_create = mocker.patch.object(CleaningService, "create_cleaning_rule")
    mock_create.return_value = _rule(3)

    response = client.post(
        "/api/v1/quality/cleaning-rules/",
        json={
            "rule_name": "Troca Av por Avenida",
            "target_column": "original_title",
            "regex_pattern": r"\bav\b\.?",
            "replacement_string": "Avenida",
        },
    )

    assert response.status_code == HTTP_201_CREATED
    body = response.json()
    assert body["data"]["rule_id"] == 3
    assert "Regra salva" in body["message"]

    dto = mock_create.call_args.args[0]
    assert dto.rule_name == "Troca Av por Avenida"
    assert dto.target_column == "original_title"
    # The controller owns created_by; the request model does not expose it.
    assert dto.created_by is None


def test_create_rule_rejects_a_column_outside_the_allowlist(client: TestClient, mocker):
    """Only the allowed ISAD(G) columns may be targeted."""
    mock_create = mocker.patch.object(CleaningService, "create_cleaning_rule")

    response = client.post(
        "/api/v1/quality/cleaning-rules/",
        json={
            "rule_name": "r",
            "target_column": "review_status",
            "regex_pattern": ".",
            "replacement_string": "",
        },
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_create.assert_not_called()


def test_create_rule_surfaces_an_invalid_regex_as_400(client: TestClient, mocker):
    """An unusable pattern is a business error, not a server failure."""
    mocker.patch.object(
        CleaningService,
        "create_cleaning_rule",
        side_effect=InvalidParam("Sintaxe de Regex inválida: nothing to repeat"),
    )

    response = client.post(
        "/api/v1/quality/cleaning-rules/",
        json={"rule_name": "r", "target_column": "original_title", "regex_pattern": "*", "replacement_string": ""},
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error_code"] == "InvalidParam"


# ==========================================
# 3. DRY RUN
# ==========================================


def test_preview_returns_the_before_and_after(client: TestClient, mocker):
    mock_dry_run = mocker.patch.object(CleaningService, "simulate_dry_run")
    mock_dry_run.return_value = DryRunResponseDTO(
        is_valid_regex=True,
        matches_found=1,
        samples=[
            DryRunMatchDTO(description_id="doc-1", original_text="av. Brasil", modified_text="Avenida Brasil"),
        ],
    )

    response = client.post(
        "/api/v1/quality/cleaning-rules/preview",
        json={"target_column": "original_title", "regex_pattern": r"\bav\b\.?", "replacement_string": "Avenida"},
    )

    assert response.status_code == HTTP_201_CREATED
    body = response.json()
    assert body["is_valid_regex"] is True
    assert body["samples"][0]["modified_text"] == "Avenida Brasil"


def test_preview_reports_an_invalid_regex_without_failing(client: TestClient, mocker):
    """The dry run is safe mode: a bad pattern is reported in the payload."""
    # The mock is the object ``patch.object`` returns, not the class attribute read back afterwards:
    # reading it back works at runtime, but the attribute's *declared* type is a function, so the
    # ``.return_value`` assignment is invisible to a type checker.
    mock_dry_run = mocker.patch.object(CleaningService, "simulate_dry_run")
    mock_dry_run.return_value = DryRunResponseDTO(is_valid_regex=False, error_message="Sintaxe de Regex inválida: *")

    response = client.post(
        "/api/v1/quality/cleaning-rules/preview",
        json={"target_column": "original_title", "regex_pattern": "*", "replacement_string": ""},
    )

    assert response.status_code == HTTP_201_CREATED
    assert response.json()["is_valid_regex"] is False


# ==========================================
# 4. DEACTIVATION
# ==========================================


def test_deactivate_rule_returns_the_updated_rule(client: TestClient, mocker):
    mock_deactivate = mocker.patch.object(CleaningService, "deactivate_rule")
    deactivated = _rule(5)
    deactivated.is_active = False
    mock_deactivate.return_value = deactivated

    response = client.patch("/api/v1/quality/cleaning-rules/5/deactivate")

    assert response.status_code == HTTP_200_OK
    assert response.json()["data"]["is_active"] is False
    mock_deactivate.assert_called_once_with(5)


def test_deactivate_missing_rule_maps_to_404(client: TestClient, mocker):
    """Regression: this used to depend on a global ValueError handler returning 400."""
    mocker.patch.object(
        CleaningService, "deactivate_rule", side_effect=CleaningRuleNotFoundError("Regra 999 não encontrada.")
    )

    response = client.patch("/api/v1/quality/cleaning-rules/999/deactivate")

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "CleaningRuleNotFoundError"


# ==========================================
# 5. REACTIVATION
# ==========================================


def test_activate_rule_returns_the_updated_rule(client: TestClient, mocker):
    """The way back: deactivating is reversible, so the screen that says so is telling the truth."""
    mock_activate = mocker.patch.object(CleaningService, "activate_rule")
    mock_activate.return_value = _rule(5)

    response = client.patch("/api/v1/quality/cleaning-rules/5/activate")

    assert response.status_code == HTTP_200_OK
    assert response.json()["data"]["is_active"] is True
    assert response.json()["code"] == "CLEANING_RULE_ACTIVATED"
    mock_activate.assert_called_once_with(5)


def test_activate_missing_rule_maps_to_404(client: TestClient, mocker):
    mocker.patch.object(
        CleaningService, "activate_rule", side_effect=CleaningRuleNotFoundError("Regra 999 não encontrada.")
    )

    response = client.patch("/api/v1/quality/cleaning-rules/999/activate")

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "CleaningRuleNotFoundError"

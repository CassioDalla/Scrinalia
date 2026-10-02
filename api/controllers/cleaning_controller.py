from litestar import Controller, get, patch, post
from litestar.di import Provide
from litestar.exceptions import NotFoundException

from api.dependencies import provide_cleaning_service
from api.schemas.cleaning_requests import CreateCleaningRuleRequest, DryRunRequest
from domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO, DryRunRequestDTO
from domains.archive.services.cleaning_service import CleaningService


class CleaningController(Controller):
    path = "/api/v1/quality/cleaning-rules"
    tags = ["Data Quality"]  # noqa: RUF012
    dependencies = {"cleaning_service": Provide(provide_cleaning_service)}  # noqa: RUF012

    # TODO RETURN DTOS

    @get("/", sync_to_thread=False)
    def list_rules(self, cleaning_service: CleaningService) -> list[dict]:
        """Returns all active rules."""
        rules = cleaning_service.get_active_rules()
        return [r.model_dump() for r in rules]

    @patch("/{rule_id:int}/deactivate")
    def deactivate_rule(self, rule_id: int, cleaning_service: CleaningService) -> dict:
        """Deactivates a rule so the Worker stops processing it."""
        try:
            rule = cleaning_service.deactivate_rule(rule_id)
            return {"message": "Regra desativada com sucesso.", "data": rule.model_dump()}
        except ValueError as e:
            raise NotFoundException(str(e)) from e

    @post("/", sync_to_thread=False)
    def create_rule(self, cleaning_service: CleaningService, data: CreateCleaningRuleRequest) -> dict:
        """Creates a new rule and activates it immediately."""

        # 2. The Controller acts as a Translator (Mapper) from the Web to the Domain
        dto = CleaningRuleCreateDTO(
            rule_name=data.rule_name,
            target_column=data.target_column,
            regex_pattern=data.regex_pattern,
            replacement_string=data.replacement_string,
            created_by=None,
        )

        new_rule = cleaning_service.create_cleaning_rule(dto)
        return {"message": "Regra salva e ativada. O Worker iniciará a varredura.", "data": new_rule.model_dump()}

    @post("/preview", sync_to_thread=False)
    def preview_dry_run(self, cleaning_service: CleaningService, data: DryRunRequest) -> dict:
        """Simulates the impact of a Regex before saving it to the database (Safe Mode)."""

        # 2. The Controller acts as a Translator (Mapper) from the Web to the Domain
        dto = DryRunRequestDTO(
            target_column=data.target_column,
            regex_pattern=data.regex_pattern,
            replacement_string=data.replacement_string,
        )

        result = cleaning_service.simulate_dry_run(dto)
        return result.model_dump()

from litestar import Controller, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath

from memoria_curitibana.api.dependencies import provide_cleaning_service
from memoria_curitibana.api.schemas.cleaning_requests import CreateCleaningRuleRequest, DryRunRequest
from memoria_curitibana.domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO, DryRunRequestDTO
from memoria_curitibana.domains.archive.services.cleaning_service import CleaningService


class CleaningController(Controller):
    path = "/api/v1/quality/cleaning-rules"
    tags = ["Data Quality"]  # noqa: RUF012
    dependencies = {"cleaning_service": Provide(provide_cleaning_service, sync_to_thread=False)}  # noqa: RUF012

    # TODO RETURN DTOS

    @get("/", sync_to_thread=True)
    def list_rules(self, cleaning_service: NamedDependency[CleaningService]) -> list[dict]:
        """Returns all active rules."""
        rules = cleaning_service.get_active_rules()
        return [r.model_dump() for r in rules]

    @patch("/{rule_id:int}/deactivate", sync_to_thread=True)
    def deactivate_rule(self, rule_id: FromPath[int], cleaning_service: NamedDependency[CleaningService]) -> dict:
        """Deactivates a rule so the Worker stops processing it."""
        rule = cleaning_service.deactivate_rule(rule_id)
        return {"message": "Regra desativada com sucesso.", "data": rule.model_dump()}

    @post("/", sync_to_thread=True)
    def create_rule(self, cleaning_service: NamedDependency[CleaningService], data: CreateCleaningRuleRequest) -> dict:
        """Creates a new rule and activates it immediately."""

        # 2. The Controller acts as a Translator (Mapper) from the Web to the Domain
        dto = CleaningRuleCreateDTO(
            rule_name=data.rule_name,
            target_column=data.target_column,
            regex_pattern=data.regex_pattern,
            replacement_string=data.replacement_string,
            rule_kind=data.rule_kind,
            anomaly_reason=data.anomaly_reason,
            engine_name=data.engine_name,
            preset=data.preset,
            created_by=None,
        )

        new_rule = cleaning_service.create_cleaning_rule(dto)
        return {"message": "Regra salva e ativada. O Worker iniciará a varredura.", "data": new_rule.model_dump()}

    @post("/preview", sync_to_thread=True)
    def preview_dry_run(self, cleaning_service: NamedDependency[CleaningService], data: DryRunRequest) -> dict:
        """Simulates the impact of a Regex before saving it to the database (Safe Mode)."""

        # 2. The Controller acts as a Translator (Mapper) from the Web to the Domain
        dto = DryRunRequestDTO(
            target_column=data.target_column,
            regex_pattern=data.regex_pattern,
            replacement_string=data.replacement_string,
        )

        result = cleaning_service.simulate_dry_run(dto)
        return result.model_dump()

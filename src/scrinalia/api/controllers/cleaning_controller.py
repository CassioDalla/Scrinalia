from litestar import Controller, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import provide_cleaning_service
from scrinalia.api.schemas.cleaning_requests import CreateCleaningRuleRequest, DryRunRequest
from scrinalia.api.security import Access
from scrinalia.domains.archive.schemas import RouteMessageCode
from scrinalia.domains.archive.schemas.cleaning_schema import (
    CleaningRuleCreateDTO,
    CleaningRuleDTO,
    CleaningRuleMutationResponse,
    DryRunRequestDTO,
    DryRunResponseDTO,
)
from scrinalia.domains.archive.services.cleaning_service import CleaningService


class CleaningController(Controller):
    path = "/api/v1/quality/cleaning-rules"
    tags = ["Data Quality"]  # noqa: RUF012
    dependencies = {"cleaning_service": Provide(provide_cleaning_service, sync_to_thread=False)}  # noqa: RUF012

    @get("/", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_rules(
        self, cleaning_service: NamedDependency[CleaningService], include_inactive: FromQuery[bool] = False
    ) -> list[CleaningRuleDTO]:
        """
        Every active rule, with its ``rule_kind``.

        The kind is the difference between cleaning and destroying: ``REWRITE`` replaces the match,
        ``VALIDATE``/``LLM_CHECK`` only flag it. A screen that listed the rules without it would make
        a validation rule look like a rewrite.

        ``include_inactive`` is what makes the retirement reversible *from the screen*: nothing here
        deletes a rule, so the way back has to be able to see the one that was retired — while the
        workers keep reading only the active ones.
        """
        return list(cleaning_service.list_rules(include_inactive=include_inactive))

    @patch("/{rule_id:int}/deactivate", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def deactivate_rule(
        self, rule_id: FromPath[int], cleaning_service: NamedDependency[CleaningService]
    ) -> CleaningRuleMutationResponse:
        """Deactivates a rule so the Worker stops processing it. Rules are never deleted."""
        rule = cleaning_service.deactivate_rule(rule_id)
        return CleaningRuleMutationResponse(
            code=RouteMessageCode.CLEANING_RULE_DEACTIVATED, message="Regra desativada com sucesso.", data=rule
        )

    @patch("/{rule_id:int}/activate", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def activate_rule(
        self, rule_id: FromPath[int], cleaning_service: NamedDependency[CleaningService]
    ) -> CleaningRuleMutationResponse:
        """Puts a deactivated rule back to work, which is what makes deactivating reversible."""
        rule = cleaning_service.activate_rule(rule_id)
        return CleaningRuleMutationResponse(
            code=RouteMessageCode.CLEANING_RULE_ACTIVATED, message="Regra reativada com sucesso.", data=rule
        )

    @post("/", opt={"access": Access.CATALOGUE}, sync_to_thread=True)
    def create_rule(
        self, cleaning_service: NamedDependency[CleaningService], data: CreateCleaningRuleRequest
    ) -> CleaningRuleMutationResponse:
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
        return CleaningRuleMutationResponse(
            code=RouteMessageCode.CLEANING_RULE_CREATED,
            message="Regra salva e ativada. O Worker iniciará a varredura.",
            data=new_rule,
        )

    @post("/preview", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def preview_dry_run(
        self, cleaning_service: NamedDependency[CleaningService], data: DryRunRequest
    ) -> DryRunResponseDTO:
        """Simulates the impact of a Regex before saving it to the database (Safe Mode)."""

        # 2. The Controller acts as a Translator (Mapper) from the Web to the Domain
        dto = DryRunRequestDTO(
            target_column=data.target_column,
            regex_pattern=data.regex_pattern,
            replacement_string=data.replacement_string,
        )

        return cleaning_service.simulate_dry_run(dto)

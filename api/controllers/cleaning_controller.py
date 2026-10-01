from litestar import Controller, get, post, patch
from litestar.di import Provide

from api.schemas.cleaning_requests import CreateCleaningRuleRequest, DryRunRequest
from domains.archive.schemas.cleaning_schema import CleaningRuleCreateDTO, DryRunRequestDTO
from litestar.exceptions import NotFoundException
from domains.archive.services.cleaning_service import CleaningService

from api.dependencies import provide_cleaning_service


class CleaningController(Controller):
    path = "/api/v1/quality/cleaning-rules"
    tags = ["Data Quality"]
    dependencies = {"cleaning_service": Provide(provide_cleaning_service)}

    # TODO RETORNAR DTOS

    @get("/", sync_to_thread=False)
    def list_rules(self, cleaning_service: CleaningService) -> list[dict]:
        """Retorna todas as regras ativas."""
        regras = cleaning_service.get_active_rules()
        return [r.model_dump() for r in regras]

    @patch("/{rule_id:int}/deactivate")
    def deactivate_rule(self, rule_id: int, cleaning_service: CleaningService) -> dict:
        """Desativa uma regra para que o Worker pare de processá-la."""
        try:
            regra = cleaning_service.deactivate_rule(rule_id)
            return {"message": "Regra desativada com sucesso.", "data": regra.model_dump()}
        except ValueError as e:
            raise NotFoundException(str(e))

    @post("/", sync_to_thread=False)
    def create_rule(self, cleaning_service: CleaningService, data: CreateCleaningRuleRequest) -> dict:
        """Cria uma nova regra e ativa-a imediatamente."""

        # 2. O Controller atua como Tradutor (Mapper) da Web para o Domínio
        dto = CleaningRuleCreateDTO(
            rule_name=data.rule_name,
            target_column=data.target_column,
            regex_pattern=data.regex_pattern,
            replacement_string=data.replacement_string,
            created_by=None,
        )

        nova_regra = cleaning_service.create_cleaning_rule(dto)
        return {"message": "Regra salva e ativada. O Worker iniciará a varredura.", "data": nova_regra.model_dump()}

    @post("/preview", sync_to_thread=False)
    def preview_dry_run(self, cleaning_service: CleaningService, data: DryRunRequest) -> dict:
        """Simula o impacto de um Regex antes de o salvar no banco (Modo de Segurança)."""

        # 2. O Controller atua como Tradutor (Mapper) da Web para o Domínio
        dto = DryRunRequestDTO(
            target_column=data.target_column,
            regex_pattern=data.regex_pattern,
            replacement_string=data.replacement_string,
        )

        resultado = cleaning_service.simulate_dry_run(dto)
        return resultado.model_dump()

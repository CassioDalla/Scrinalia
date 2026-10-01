import re

from domains.archive.exceptions import InvalidParam
from domains.archive.repository.cleaning_repo import CleaningRepository
from domains.archive.schemas.cleaning_schema import (
    CleaningRuleCreateDTO,
    CleaningRuleDTO,
    DryRunMatchDTO,
    DryRunRequestDTO,
    DryRunResponseDTO,
)


class CleaningService:
    def __init__(self, repo: CleaningRepository):
        self.repo = repo

    def _validate_regex(self, pattern: str) -> re.Pattern:
        """Tenta compilar o Regex. Se falhar, lança erro de negócio."""
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise InvalidParam(f"Sintaxe de Regex inválida: {e!s}") from e

    def create_cleaning_rule(self, dto: CleaningRuleCreateDTO) -> CleaningRuleDTO:
        # Validação antecipada (Fail Fast)
        self._validate_regex(dto.regex_pattern)

        rule = self.repo.create_rule(dto.model_dump())
        return CleaningRuleDTO.model_validate(rule, from_attributes=True)

    def simulate_dry_run(self, dto: DryRunRequestDTO) -> DryRunResponseDTO:
        """
        Pega o Regex do utilizador, carrega documentos reais e mostra o "Antes e Depois"
        para ele ter certeza de que não vai destruir o banco de dados sem querer.
        """
        try:
            regex = self._validate_regex(dto.regex_pattern)
        except InvalidParam as e:
            return DryRunResponseDTO(is_valid_regex=False, error_message=str(e))

        docs = self.repo.get_random_sample_for_dry_run(dto.target_column, limit=300)

        matches = []
        for doc in docs:
            texto_original = getattr(doc, dto.target_column)

            # Se o Regex encontrar algo neste texto
            if texto_original and regex.search(texto_original):
                texto_modificado = regex.sub(dto.replacement_string, texto_original)

                # Guarda apenas se houve uma modificação real
                if texto_original != texto_modificado:
                    matches.append(
                        DryRunMatchDTO(
                            description_id=doc.description_id,
                            original_text=texto_original,
                            modified_text=texto_modificado,
                        )
                    )

                    # Limitamos a 5 exemplos visuais para não sobrecarregar a API
                    if len(matches) >= 5:
                        break

        return DryRunResponseDTO(is_valid_regex=True, matches_found=len(matches), samples=matches)

    def get_active_rules(self) -> list[CleaningRuleDTO]:
        rules = self.repo.get_active_rules()
        return [CleaningRuleDTO.model_validate(r, from_attributes=True) for r in rules]

    def deactivate_rule(self, rule_id: int) -> CleaningRuleDTO:

        rule = self.repo.get_rule_by_id(rule_id=rule_id)
        if not rule:
            raise ValueError(f"Regra {rule_id} não encontrada.")

        rule.is_active = False
        self.repo.db.commit()

        return CleaningRuleDTO.model_validate(rule, from_attributes=True)

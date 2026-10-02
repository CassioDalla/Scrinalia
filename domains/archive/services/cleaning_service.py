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
        """Tries to compile the Regex. If the compile fails, raises a business error."""
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise InvalidParam(f"Sintaxe de Regex inválida: {e!s}") from e

    def create_cleaning_rule(self, dto: CleaningRuleCreateDTO) -> CleaningRuleDTO:
        # Early validation (Fail Fast)
        self._validate_regex(dto.regex_pattern)

        rule = self.repo.create_rule(dto.model_dump())
        return CleaningRuleDTO.model_validate(rule, from_attributes=True)

    def simulate_dry_run(self, dto: DryRunRequestDTO) -> DryRunResponseDTO:
        """
        Takes the user's Regex, loads real documents and shows the "Before and After"
        so they can be sure they will not accidentally destroy the database.
        """
        try:
            regex = self._validate_regex(dto.regex_pattern)
        except InvalidParam as e:
            return DryRunResponseDTO(is_valid_regex=False, error_message=str(e))

        docs = self.repo.get_random_sample_for_dry_run(dto.target_column, limit=300)

        matches = []
        for doc in docs:
            original_text = getattr(doc, dto.target_column)

            # If the Regex finds something in this text
            if original_text and regex.search(original_text):
                modified_text = regex.sub(dto.replacement_string, original_text)

                # Only saves if there was a real modification
                if original_text != modified_text:
                    matches.append(
                        DryRunMatchDTO(
                            description_id=doc.description_id,
                            original_text=original_text,
                            modified_text=modified_text,
                        )
                    )

                    # We limit it to 5 visual examples to avoid overloading the API
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
        # The transaction is owned by the caller (API middleware or worker context):
        # the service must not commit on its own.
        self.repo.db.flush()

        return CleaningRuleDTO.model_validate(rule, from_attributes=True)

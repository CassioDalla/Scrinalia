import re

from scrinalia.domains.archive.exceptions import CleaningRuleNotFoundError, InvalidParam
from scrinalia.domains.archive.ports.cleaning import CleaningRepositoryPort
from scrinalia.domains.archive.schemas.cleaning_schema import (
    CleaningRuleCreateDTO,
    CleaningRuleDTO,
    DryRunMatchDTO,
    DryRunRequestDTO,
    DryRunResponseDTO,
)


class CleaningService:
    def __init__(self, repo: CleaningRepositoryPort):
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
        return self.repo.create_rule(dto)

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
            original_text = doc.text

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

    def get_active_rules(self, rule_kind: str | None = None) -> list[CleaningRuleDTO]:
        return list(self.repo.get_active_rules(rule_kind=rule_kind))  # type: ignore[arg-type]

    def deactivate_rule(self, rule_id: int) -> CleaningRuleDTO:
        # The transaction is owned by the caller (API middleware or worker context):
        # the repository flushes and the use case never commits on its own.
        rule = self.repo.deactivate_rule(rule_id)
        if rule is None:
            raise CleaningRuleNotFoundError(f"Regra {rule_id} não encontrada.")

        return rule

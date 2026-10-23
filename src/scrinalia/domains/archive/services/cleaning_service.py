import re
from typing import cast

from scrinalia.domains.archive.exceptions import (
    CleaningRuleNotFoundError,
    InvalidLLMCheckEngineError,
    InvalidParam,
)
from scrinalia.domains.archive.ports.cleaning import CleaningRepositoryPort
from scrinalia.domains.archive.schemas.cleaning_schema import (
    CleaningRuleCreateDTO,
    CleaningRuleDTO,
    DryRunMatchDTO,
    DryRunRequestDTO,
    DryRunResponseDTO,
)
from scrinalia.domains.archive.workers.catalogue import DEFAULT_LLM_CHECK_ENGINE


class CleaningService:
    def __init__(self, repo: CleaningRepositoryPort):
        self.repo = repo

    def _validate_regex(self, pattern: str) -> re.Pattern:
        """Tries to compile the Regex. If the compile fails, raises a business error."""
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise InvalidParam(f"Sintaxe de Regex inválida: {e!s}") from e

    def _validate_engine(self, dto: CleaningRuleCreateDTO) -> None:
        """
        Refuses an engine/preset pair the title-quality registry cannot build, at the door.

        The check runs whenever either field is present, whatever the ``rule_kind`` is: the pair is
        validated where it would be used, so a ``REWRITE`` rule carrying one is not a hole. An empty
        ``engine_name`` stays legal — it means the worker's documented fallback — and a preset with
        no engine is validated against that same fallback engine, which is the pair the run resolves.

        The refusal is a ``DomainException`` and not the registry's ``ValueError``: the API owes a
        business status, and the registry's own sentence already names the options (#124).
        """
        if dto.engine_name is None and dto.preset is None:
            return

        # Function-level import, like the worker's own: touching an engine registry is what pulls the
        # axis's stack, and the cleaning catalogue is read by requests that never build an engine.
        from scrinalia.domains.archive.engines.title_quality.registry import (
            EngineName,
            PresetName,
            describe_config,
        )

        # The pair arrives as free text — that is the whole defect #124 — so the cast is the point
        # where an unvalidated string meets the registry that decides whether it exists.
        engine_name = dto.engine_name or DEFAULT_LLM_CHECK_ENGINE
        try:
            describe_config(cast("EngineName", engine_name), cast("PresetName | None", dto.preset))
        except ValueError as e:
            raise InvalidLLMCheckEngineError(str(e)) from e

    def create_cleaning_rule(self, dto: CleaningRuleCreateDTO) -> CleaningRuleDTO:
        # Early validation (Fail Fast)
        self._validate_regex(dto.regex_pattern)
        self._validate_engine(dto)
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

    def list_rules(self, *, include_inactive: bool = False) -> list[CleaningRuleDTO]:
        """The catalogue for the screen; the workers keep reading only the active ones."""
        return list(self.repo.list_rules(include_inactive=include_inactive))

    def deactivate_rule(self, rule_id: int) -> CleaningRuleDTO:
        # The transaction is owned by the caller (API middleware or worker context):
        # the repository flushes and the use case never commits on its own.
        rule = self.repo.deactivate_rule(rule_id)
        if rule is None:
            raise CleaningRuleNotFoundError(f"Regra {rule_id} não encontrada.")

        return rule

    def activate_rule(self, rule_id: int) -> CleaningRuleDTO:
        """Returns the rule to the queue the worker reads.

        It exists because deactivating had no way back: the rule was never deleted, but nothing
        could put it to work again, so trying a rule once was a final decision.
        """
        rule = self.repo.activate_rule(rule_id)
        if rule is None:
            raise CleaningRuleNotFoundError(f"Regra {rule_id} não encontrada.")

        return rule

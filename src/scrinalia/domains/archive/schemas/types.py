"""
Pydantic value objects for normalized names.

Applying these at the input DTOs makes the canonical spelling (trimmed,
lowercase) a property of the schema, so a raw name can never enter the
domain unnormalized.
"""

from typing import Annotated

from pydantic import AfterValidator

from scrinalia.domains.archive.domain.normalization import normalize_entity, normalize_synonym, normalize_tag

TagName = Annotated[str, AfterValidator(normalize_tag)]
EntityName = Annotated[str, AfterValidator(normalize_entity)]
SynonymName = Annotated[str, AfterValidator(normalize_synonym)]

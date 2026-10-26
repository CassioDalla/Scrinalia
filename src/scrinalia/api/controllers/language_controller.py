"""HTTP surface of the language catalogue."""

from litestar import Controller, get

from scrinalia.api.security import Access
from scrinalia.domains.archive.domain.language_catalog import LANGUAGES
from scrinalia.domains.archive.schemas.language_schema import LanguageDTO


class LanguageController(Controller):
    """
    The languages a description may declare.

    Read-only on purpose: the list is declared in code (:mod:`scrinalia.domains.archive.domain.
    language_catalog`) because a language carries no rule an institution edits — unlike a typology,
    which the classifier reads as a candidate label, or an arrangement rung, which states whether it
    requires a parent. The screen that needs the options asks for them here, so the names exist
    once and the form and the dossier cannot disagree about them.

    There is no write route, and none is planned: adding a language is a line in the catalogue and a
    test. A facet by language is the trigger that would turn it into a table, with its own screen.
    """

    path = "/api/v1/languages"
    tags = ["Languages"]  # noqa: RUF012

    @get("/", opt={"access": Access.AUTHENTICATED}, sync_to_thread=False)
    def list_languages(self) -> list[LanguageDTO]:
        """Every language of the catalogue, in the order the select shows them."""
        return [LanguageDTO(code=language.code, name=language.name) for language in LANGUAGES]

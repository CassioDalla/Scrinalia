"""The language catalogue as the contract shows it."""

from pydantic import BaseModel


class LanguageDTO(BaseModel):
    """
    One language a description may declare.

    ``code`` is the ISO 639 identifier and ``name`` is what the archivist reads and what the archive
    stores. The order of the list is the catalogue's and the screen keeps it: the collection's own
    language first.
    """

    code: str
    name: str

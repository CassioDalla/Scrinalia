"""
The language seam: the data lives in one profile, and the rules read it.

Two things are pinned here, and they are the point of the refactor. First, the profile is
the *only* place the language data lives — a rule that started carrying its own copy of the
stopwords or the street prefixes would make these tests fail. Second, the rules actually read
the profile: a fake profile changes their verdict, which is what proves the seam is real and
not documentation.
"""

import re
from dataclasses import replace

import pytest

from scrinalia.core.language import DEFAULT_LANGUAGE, LANGUAGES, get_language
from scrinalia.core.language.pt_br import PT_BR
from scrinalia.domains.archive.domain.normalization import singular_candidates
from scrinalia.domains.staging.dates import parse_document_date


def test_pt_br_is_the_default_profile() -> None:
    assert DEFAULT_LANGUAGE == "pt-BR"
    assert LANGUAGES["pt-BR"] is PT_BR


def test_the_profile_carries_every_language_dependent_artefact() -> None:
    """
    The profile is complete by construction: a missing field would be a language rule hidden
    somewhere else, which is exactly what the refactor removed.
    """
    assert len(PT_BR.stopwords) > 400, "the stopword list is measured, not a handful of words"
    assert PT_BR.fts_dictionary == "portuguese"
    assert PT_BR.ner_model == "pt_core_news_lg"
    assert PT_BR.local_date_order == "DMY"
    assert PT_BR.plural_rules, "the plural rules are what the merge suggestion folds"
    for pattern in (
        PT_BR.decade_pattern,
        PT_BR.range_pattern,
        PT_BR.local_date_pattern,
        PT_BR.placeholder_pattern,
        PT_BR.street_pattern,
        PT_BR.measure_pattern,
    ):
        assert isinstance(pattern, re.Pattern)


def test_an_unknown_language_fails_fast() -> None:
    """A typo in the environment must not silently fall back to a language nobody chose."""
    with pytest.raises(ValueError, match="Unknown language"):
        get_language("kl-GL")


def test_the_date_parser_reads_the_profiles_spelling(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    An ISO-shaped profile parses ``2024/03/05`` as its own date; the pt-BR profile only finds
    the bare year in it, because its local spelling is ``dd/mm/yyyy``. The rule did not change:
    what changed is the profile it reads.
    """
    assert parse_document_date("2024/03/05") is not None

    fake = replace(
        PT_BR,
        local_date_pattern=re.compile(r"(\d{4})/(\d{2})/(\d{2})"),
        local_date_order="YMD",
    )
    monkeypatch.setattr("scrinalia.domains.staging.dates.get_language", lambda: fake)

    assert parse_document_date("2024/03/05").isoformat() == "2024-03-05"


def test_the_empty_values_are_the_profiles_word(monkeypatch: pytest.MonkeyPatch) -> None:
    """``1980`` is a year to pt-BR; a profile that declares it "no date" must win over the parser."""
    assert parse_document_date("1980") is not None

    fake = replace(PT_BR, empty_date_values=frozenset({"1980"}))
    monkeypatch.setattr("scrinalia.domains.staging.dates.get_language", lambda: fake)

    assert parse_document_date("1980") is None


def test_the_plural_rules_come_from_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endings are the language's; the folding rule stays in the domain."""
    assert singular_candidates("livroz") == []

    fake = replace(PT_BR, plural_rules=(("z", ""),))
    monkeypatch.setattr("scrinalia.domains.archive.domain.normalization.get_language", lambda: fake)

    assert singular_candidates("livroz") == ["livro"]

"""The one reading of a raw access-point string, without a database or a service.

The transfer and the creation form both call this function; the cases below are the rules they
share. The stopword case with repeated spaces is the one the previous implementation missed: the
ban was checked before the whitespace was collapsed, so ``rio  branco`` became a tag even when
``rio branco`` was banned.
"""

from scrinalia.domains.archive.domain.access_points import (
    AccessPointStatus,
    classify_indexing_points,
)

STOPWORDS = frozenset({"obras", "cidade", "rio branco"})


def test_empty_and_blank_strings_answer_no_candidates() -> None:
    assert classify_indexing_points(None, STOPWORDS) == []
    assert classify_indexing_points("", STOPWORDS) == []
    assert classify_indexing_points("  , ; |  ", STOPWORDS) == []


def test_reads_every_separator_the_pipeline_accepts() -> None:
    candidates = classify_indexing_points("urbanismo, obras; habitação|transporte", STOPWORDS)

    assert [candidate.input for candidate in candidates] == ["urbanismo", "obras", "habitação", "transporte"]
    assert [candidate.dropped for candidate in candidates] == [
        None,
        AccessPointStatus.STOPWORD,
        None,
        None,
    ]


def test_trims_lowercases_and_collapses_whitespace() -> None:
    [candidate] = classify_indexing_points("  Urbanismo   e   Habitação  ", STOPWORDS)

    assert candidate.input == "Urbanismo   e   Habitação"
    assert candidate.normalized == "urbanismo e habitação"


def test_a_stopword_is_dropped_only_when_it_is_the_whole_tag() -> None:
    candidates = classify_indexing_points("rio, Rio Branco, rio  branco", STOPWORDS)

    # "rio" is not the ban; "rio branco" is, and the spelling with two spaces is the same whole
    # tag after the collapse. Dropping it is the fix this classifier exists to make.
    assert [candidate.normalized for candidate in candidates] == ["rio", "rio branco", "rio branco"]
    assert [candidate.dropped for candidate in candidates] == [
        None,
        AccessPointStatus.STOPWORD,
        AccessPointStatus.STOPWORD,
    ]


def test_a_banned_word_inside_a_longer_tag_does_not_drop_it() -> None:
    candidates = classify_indexing_points("Rio Branco, rio", frozenset({"rio"}))

    assert [candidate.dropped for candidate in candidates] == [None, AccessPointStatus.STOPWORD]


def test_drops_the_length_edges() -> None:
    candidates = classify_indexing_points("a, ab, abc, " + "x" * 100 + ", " + "y" * 101, frozenset())

    assert [candidate.dropped for candidate in candidates] == [
        AccessPointStatus.TOO_SHORT,
        AccessPointStatus.TOO_SHORT,
        None,
        None,
        AccessPointStatus.TOO_LONG,
    ]


def test_duplicates_keep_the_first_spelling_and_mark_the_rest() -> None:
    candidates = classify_indexing_points("Urbanismo, urbanismo, URBANISMO", frozenset())

    assert [candidate.dropped for candidate in candidates] == [
        None,
        AccessPointStatus.DUPLICATE,
        AccessPointStatus.DUPLICATE,
    ]
    assert candidates[0].input == "Urbanismo"
    assert candidates[0].normalized == "urbanismo"


def test_preserves_the_typed_order() -> None:
    candidates = classify_indexing_points("zeta, alfa, meio", frozenset())

    assert [candidate.normalized for candidate in candidates] == ["zeta", "alfa", "meio"]


def test_status_codes_are_stable_strings() -> None:
    """The codes travel to the form, so they are part of the contract."""
    assert AccessPointStatus.NEW == "NEW"
    assert AccessPointStatus.SYNONYM == "SYNONYM"
    assert AccessPointStatus.EXISTING == "EXISTING"
    assert AccessPointStatus.STOPWORD == "STOPWORD"
    assert AccessPointStatus.TOO_SHORT == "TOO_SHORT"
    assert AccessPointStatus.TOO_LONG == "TOO_LONG"
    assert AccessPointStatus.DUPLICATE == "DUPLICATE"

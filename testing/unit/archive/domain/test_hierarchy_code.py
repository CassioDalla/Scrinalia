"""
The vocabulary-aware slicer, against the codes the real collection actually carries.

Every case here was read from the 3,608 descriptions. The one that decides the design is the SMU
family: ``BR PRADAP SMU ED AL CONSTR 2154 1903`` holds **1,123 documents**, and slicing it on every
space would turn ``BR PRADAP SMU ED AL`` into 1,123 parents of one document each. The code
interleaves the arrangement vocabulary with the identifiers of the leaf; this module is where the
two are told apart, and the assertions below are what stops the naive slicing from coming back.
"""

import pytest

from scrinalia.domains.archive.domain.hierarchy_code import (
    CodeFlag,
    is_structural_token,
    normalize_reference_code,
    slice_reference_code,
    tokenize,
)


class TestTheTwoRealFamilies:
    def test_the_photograph_rung_contracts_the_serial(self) -> None:
        sliced = slice_reference_code("BR PRADAP IPPUC FOTOGRAFIA 00680")
        assert sliced.structural_code == "BR PRADAP IPPUC FOTOGRAFIA"
        assert sliced.dropped_tail == ("00680",)
        assert sliced.is_clean

    def test_the_smu_rung_contracts_the_process_and_the_year(self) -> None:
        """The 1,123-document family: two identifiers belong to the leaf, not to a rung."""
        sliced = slice_reference_code("BR PRADAP SMU ED AL CONSTR 2154 1903")
        assert sliced.structural_code == "BR PRADAP SMU ED AL CONSTR"
        assert sliced.dropped_tail == ("2154", "1903")
        assert sliced.is_clean

    def test_the_smu_branch_does_not_explode_into_one_parent_per_document(self) -> None:
        """
        The regression that motivated the whole module.

        ``BR PRADAP SMU ED AL`` is a rung shared by 1,123 documents, and the naive slice would have
        made each document its own node one level below it.
        """
        codes = [
            slice_reference_code(f"BR PRADAP SMU ED AL CONSTR {serial} {year}").structural_code
            for serial, year in (("2154", "1903"), ("1685", "1917"), ("319", "1924"))
        ]
        assert set(codes) == {"BR PRADAP SMU ED AL CONSTR"}

    def test_the_series_record_is_a_pure_rung(self) -> None:
        """``BR PRADAP IPPUC FOTOGRAFIAS`` declares the arrangement and nothing else."""
        sliced = slice_reference_code("BR PRADAP IPPUC FOTOGRAFIAS")
        assert sliced.structural_code == "BR PRADAP IPPUC FOTOGRAFIAS"
        assert sliced.dropped_tail == ()

    def test_the_plural_and_the_singular_are_different_codes(self) -> None:
        """
        The trap the roadmap warns about: one letter apart, and a trigram merge would join them.

        The slicer must keep them apart, because only a human can say whether the 2,391 items hang
        from the existing Série or need a node of their own.
        """
        singular = slice_reference_code("BR PRADAP IPPUC FOTOGRAFIA 00680").structural_code
        plural = slice_reference_code("BR PRADAP IPPUC FOTOGRAFIAS").structural_code
        assert singular != plural
        assert singular == "BR PRADAP IPPUC FOTOGRAFIA"
        assert plural == "BR PRADAP IPPUC FOTOGRAFIAS"


class TestTheMalformedCodesAreFlaggedNotSwallowed:
    """~20 of the 3,608 codes carry a tail that is not a clean serial; each is listed, not hidden."""

    @pytest.mark.parametrize(
        "raw_code, structural, tail",
        [
            ("BR PRADAP SMU ED AL CONSTR 10047 (1)", "BR PRADAP SMU ED AL CONSTR", ("10047", "(1)")),
            ("BR PRADAP SMU ED AL CONSTR 11925_1916", "BR PRADAP SMU ED AL CONSTR", ("11925_1916",)),
            ("BR PRADAP SMU ED AL CONSTR 369B", "BR PRADAP SMU ED AL CONSTR", ("369B",)),
            ("BR PRADAP SMU ED AL CONSTR 998-1", "BR PRADAP SMU ED AL CONSTR", ("998-1",)),
            ("BR PRADAP SMU ED AL CONSTR 1869 (II)", "BR PRADAP SMU ED AL CONSTR", ("1869", "(II)")),
        ],
    )
    def test_a_tail_that_is_not_a_number_is_flagged(
        self, raw_code: str, structural: str, tail: tuple[str, ...]
    ) -> None:
        sliced = slice_reference_code(raw_code)
        assert sliced.structural_code == structural
        assert sliced.dropped_tail == tail
        assert CodeFlag.UNPARSED_TAIL in sliced.flags
        assert not sliced.is_clean

    def test_a_year_in_the_middle_is_flagged_and_kept(self) -> None:
        """
        ``BR PRADAP SEPLAD OF 478 1959 DUP`` has the identifier *before* the last vocabulary token.

        Dropping it would invent a rung; keeping it quietly would invent one too. So it stays in the
        path and the code is flagged — the archivist decides.
        """
        sliced = slice_reference_code("BR PRADAP SEPLAD OF 478 1959 DUP")
        assert CodeFlag.MID_CODE_IDENTIFIER in sliced.flags
        assert "478" in sliced.structural

    def test_a_code_without_any_vocabulary_is_reported(self) -> None:
        sliced = slice_reference_code("123 456")
        assert sliced.structural == ()
        assert CodeFlag.NO_STRUCTURAL_TOKEN in sliced.flags


class TestTokenization:
    def test_double_spaces_do_not_create_empty_tokens(self) -> None:
        assert tokenize("BR  PRADAP   SMU") == ("BR", "PRADAP", "SMU")

    def test_nbsp_is_a_separator(self) -> None:
        """The real payloads carry U+00A0, and ``\\s`` does not cover it in every engine."""
        assert tokenize("BR\u00a0PRADAP SMU") == ("BR", "PRADAP", "SMU")

    def test_normalisation_collapses_spacing_and_case_but_keeps_punctuation(self) -> None:
        assert normalize_reference_code("  br   pradap smu  ") == "BR PRADAP SMU"
        # ``369B`` and ``998-1`` are real codes: folding them would collide two descriptions.
        assert normalize_reference_code("br pradap smu ed al constr 369b") == "BR PRADAP SMU ED AL CONSTR 369B"

    def test_accents_are_vocabulary(self) -> None:
        assert is_structural_token("LEGISLAÇÃO")
        assert not is_structural_token("00680")


class TestTheRungsACodeImplies:
    def test_every_container_of_the_code_is_listed_root_first(self) -> None:
        sliced = slice_reference_code("BR PRADAP SMU ED AL CONSTR 2154 1903")
        assert sliced.rungs() == (
            "BR PRADAP",
            "BR PRADAP SMU",
            "BR PRADAP SMU ED",
            "BR PRADAP SMU ED AL",
            "BR PRADAP SMU ED AL CONSTR",
        )

    def test_the_root_code_is_its_own_single_rung(self) -> None:
        """``BR PRADAP`` is the Acervo and nothing above it: the ladder starts there."""
        assert slice_reference_code("BR PRADAP").rungs() == ("BR PRADAP",)

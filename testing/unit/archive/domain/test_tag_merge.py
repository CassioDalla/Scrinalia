from scrinalia.domains.archive.domain.tag_merge import (
    REVIEW_MEMBER_WITH_DIGITS,
    cluster_fingerprint,
    has_digits,
)


def test_cluster_fingerprint_ignores_member_order() -> None:
    """The union-find order must not create a second proposal for the same set of names."""
    assert cluster_fingerprint("casa", ["casa", "casas"]) == cluster_fingerprint("casa", ["casas", "casa"])


def test_cluster_fingerprint_changes_with_the_composition() -> None:
    """A new member is a new decision: the cluster has to be reviewed again."""
    assert cluster_fingerprint("casa", ["casa", "casas"]) != cluster_fingerprint("casa", ["casa", "casas", "casa."])


def test_cluster_fingerprint_separates_different_canonicals() -> None:
    """The same members under another canonical are another proposal."""
    assert cluster_fingerprint("casa", ["casa", "casas"]) != cluster_fingerprint("casas", ["casa", "casas"])


def test_cluster_fingerprint_is_stable_across_casing_and_spacing() -> None:
    """Identity is about the spelling, so " Casa " and "casa" are the same proposal."""
    assert cluster_fingerprint(" Casa ", [" Casas "]) == cluster_fingerprint("casa", ["casas"])


def test_has_digits_flags_the_measured_false_positives() -> None:
    """The number-bearing spellings are where the wrong proposals concentrate."""
    assert has_digits("rua 7")
    assert has_digits("303 anos")
    assert has_digits("br-116")
    assert not has_digits("rua")


def test_review_flag_codes_are_stable_strings() -> None:
    """The flag travels to the client, so the code is part of the contract."""
    assert REVIEW_MEMBER_WITH_DIGITS == "MEMBER_WITH_DIGITS"

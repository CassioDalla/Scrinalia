"""The pair of columns an author writes, and the two ways of writing it.

Small enough to look trivial, and the place where the failure would be silent: a row with a name and
somebody else's id looks *more* trustworthy than a row with no id at all, so the two halves have one
definition and this is what pins it.
"""

from dataclasses import dataclass

from scrinalia.core.author import Author, assign_author, author_columns


def test_the_pair_carries_the_name_and_the_account() -> None:
    assert author_columns("changed_by", Author(name="Maria", user_id=7)) == {
        "changed_by": "Maria",
        "changed_by_user_id": 7,
    }


def test_no_author_writes_two_nulls_and_not_one() -> None:
    """The CLI's run with no ``--by``, and any legacy caller: both columns absent, never half a pair."""
    assert author_columns("requested_by", None) == {"requested_by": None, "requested_by_user_id": None}


def test_an_author_without_an_account_keeps_the_name() -> None:
    """The host's ``--by "fulano"``: a claim, recorded as one, with no id pretending otherwise."""
    assert author_columns("decided_by", Author(name="fulano")) == {
        "decided_by": "fulano",
        "decided_by_user_id": None,
    }


def test_the_base_name_is_the_only_thing_that_changes() -> None:
    """Every ledger keeps the column name it always had, so the read contracts did not move."""
    for base in ("changed_by", "decided_by", "deleted_by", "created_by", "requested_by"):
        assert set(author_columns(base, None)) == {base, f"{base}_user_id"}


@dataclass
class _Row:
    changed_by: str | None = None
    changed_by_user_id: int | None = None


def test_assign_author_writes_the_same_pair_on_an_existing_row() -> None:
    row = _Row()

    assign_author(row, "changed_by", Author(name="Maria", user_id=7))

    assert (row.changed_by, row.changed_by_user_id) == ("Maria", 7)


def test_assign_author_clears_both_when_there_is_none() -> None:
    row = _Row(changed_by="Maria", changed_by_user_id=7)

    assign_author(row, "changed_by", None)

    assert (row.changed_by, row.changed_by_user_id) == (None, None)

"""Who acted, as the ledgers record it.

Both halves of an act's authorship are needed, and they are not the same fact:

* the **name** is what the ledger prints. A revision says "Maria" because that is what somebody
  reading the history recognises, and it is a *snapshot*: renaming an account does not rewrite the
  past, and it should not — the row records what was true when the decision was taken.
* the **id** is the durable link. It is what makes "everything this account decided" answerable, and
  what keeps the trail meaningful after a rename or a deactivation.

It lives in ``core`` and not in ``domains/identity`` because the archive's ledgers are the ones that
carry it, and a domain must not import another domain. The same argument that moved
``DomainException`` here: the concept is shared, only its first address was domain-specific.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Author:
    """
    One act's author.

    ``user_id`` is ``None`` for an act that has no account behind it — the worker runner invoked from
    the host with ``--by "fulano"``. That is a deliberate asymmetry and not an oversight: the CLI runs
    on the server, outside the HTTP threat model, so its free-text author is honest about being a
    claim rather than an authenticated identity.
    """

    name: str
    user_id: int | None = None


def author_columns(base: str, author: Author | None) -> dict[str, object]:
    """
    The pair of columns every ledger writes for one act's author.

    ``base`` is the name the table has always used — ``changed_by``, ``decided_by``, ``deleted_by``,
    ``created_by``, ``requested_by`` — and the second column is always ``<base>_user_id``. One
    function for the pair, because the two going out of step is the failure that would not be
    noticed: a row with a name and somebody else's id looks *more* trustworthy than one with no id at
    all.
    """
    return {base: author.name if author else None, f"{base}_user_id": author.user_id if author else None}


def assign_author(row: object, base: str, author: Author | None) -> None:
    """The same pair, for a row that already exists and is being mutated instead of constructed."""
    for column, value in author_columns(base, author).items():
        setattr(row, column, value)

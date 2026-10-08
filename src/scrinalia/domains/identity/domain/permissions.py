"""The two vocabularies of authorization: what a person is, and what an area allows.

The map lives here, in code, and not in a table. An editable permission matrix is a second place
where authorization can be wrong, and it answers a question this system does not have: an archive
needs three answers — who reads, who curates, who operates the installation — not a role composer.
Adding a permission is a line here plus the routes that declare it; adding a role is a decision that
should be read in a diff.
"""

from __future__ import annotations

import enum


class Role(enum.StrEnum):
    """
    The three answers an archive actually needs.

    ``ADMIN`` is not "a curator with more buttons": it owns the two things that belong to the
    *installation* rather than to the collection — the accounts and the AI workers. Triggering a
    worker costs CPU for minutes, and changing its preset changes every future classification, so it
    is deliberately not something a curation account does by accident. ``CURATOR`` is the archivist
    who decides about descriptions, subjects and catalogues. ``VIEWER`` reads everything and writes
    nothing: the colleague who needs to consult the collection without being able to alter it.
    """

    ADMIN = "ADMIN"
    CURATOR = "CURATOR"
    VIEWER = "VIEWER"


class Permission(enum.StrEnum):
    """An area of the system a request can write to, or a read that is about the installation."""

    #: The record and its subjects: the ISAD(G) fields, tags, entities, conflicts and the ledgers.
    CURATE = "CURATE"
    #: The closed catalogues the collection is described against: levels, typologies, vocabulary,
    #: cleaning rules and text excerpts. Maintaining a catalogue is not the same as curating one
    #: record — it changes how every future record is described — which is why it is its own area.
    CATALOGUE = "CATALOGUE"
    #: The AI workers: triggering a run, overriding an engine or a preset, and reading the health
    #: panel that names the models. It is the only area where a request can cost minutes of CPU.
    OPERATE = "OPERATE"
    #: Accounts and sessions.
    ADMIN = "ADMIN"


#: What each role carries **beyond reading**. There is no ``READ`` permission on purpose: reading is
#: what an authenticated session is, and inventing a permission for it would make "logged in" and
#: "allowed to read" two things that can disagree.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({Permission.CURATE, Permission.CATALOGUE, Permission.OPERATE, Permission.ADMIN}),
    Role.CURATOR: frozenset({Permission.CURATE, Permission.CATALOGUE}),
    Role.VIEWER: frozenset(),
}


def has_permission(role: Role, permission: Permission) -> bool:
    """
    Whether ``role`` carries ``permission``.

    Deny by default in both directions: an unknown role grants nothing (``.get`` with an empty
    default), and a permission missing from every role's set is granted to nobody.
    """
    return permission in ROLE_PERMISSIONS.get(role, frozenset())

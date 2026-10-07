"""The role map, pinned as a table.

Authorization is the one thing in this system whose failure is silent: a role that carries a
permission it should not looks exactly like a role that does not, until somebody triggers a worker.
So the map is asserted member by member rather than by a sample, and the last test asserts the
property that makes the vocabulary honest — no permission exists that nobody can exercise.
"""

from typing import cast

import pytest

from scrinalia.domains.identity.domain.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    has_permission,
)

#: What each role may do, written out here on purpose: the test is the second reader of the map, and
#: a diff that widens a role has to change this table too.
EXPECTED = {
    Role.ADMIN: {Permission.CURATE, Permission.CATALOGUE, Permission.OPERATE, Permission.ADMIN},
    Role.CURATOR: {Permission.CURATE, Permission.CATALOGUE},
    Role.VIEWER: set(),
}


@pytest.mark.parametrize("role", list(Role))
def test_each_role_carries_exactly_what_it_should(role: Role) -> None:
    assert set(ROLE_PERMISSIONS[role]) == EXPECTED[role]


def test_every_role_is_in_the_map() -> None:
    """A new role that nobody wrote a permission line for would otherwise grant nothing silently."""
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_the_curator_cannot_operate_the_workers() -> None:
    """
    The line that matters most in this map.

    Triggering a worker costs minutes of CPU and changing its preset changes every future
    classification; a curation account must not be able to do either by accident.
    """
    assert has_permission(Role.CURATOR, Permission.OPERATE) is False
    assert has_permission(Role.CURATOR, Permission.ADMIN) is False
    assert has_permission(Role.ADMIN, Permission.OPERATE) is True


def test_a_viewer_carries_nothing_beyond_reading() -> None:
    assert all(has_permission(Role.VIEWER, permission) is False for permission in Permission)


def test_an_unknown_role_grants_nothing() -> None:
    """Deny by default: the answer for a value the database should never hold is still "no"."""
    assert has_permission(cast(Role, "SUPERUSER"), Permission.CURATE) is False


def test_no_permission_is_dead_vocabulary() -> None:
    """A permission no role carries is a route that would refuse everyone, including the admin."""
    granted = {permission for permissions in ROLE_PERMISSIONS.values() for permission in permissions}
    assert granted == set(Permission)

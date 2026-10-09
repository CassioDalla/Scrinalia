"""The first-run routes as HTTP: an empty installation brought to life, and the door closing behind it.

What is asserted here is the contract the installer and the SPA read — what ``/status`` says, what
``/admin`` answers, that the account it creates is signed in and does not owe a password change, and
that the refusal after the first call is a 409 and not a 500. The **atomicity** of the write is a
property of the table lock and is pinned against two real connections in
``testing/integration/identity/test_first_admin_race.py``; an HTTP test cannot see it, because the
suite's client shares the test's single transaction.
"""

from litestar.testing import TestClient

from scrinalia.domains.identity.domain.permissions import Role

EMAIL = "ana@instituicao.org"
NAME = "Ana Arquivista"
PASSWORD = "uma senha bem longa"


def _create(client: TestClient, **overrides):
    return client.post(
        "/api/v1/setup/admin",
        json={"email": EMAIL, "name": NAME, "password": PASSWORD, **overrides},
    )


# ==========================================
# WHAT THE INSTALLATION SAYS ABOUT ITSELF
# ==========================================


def test_an_empty_installation_says_it_needs_setup(api_client: TestClient) -> None:
    """The one fact an anonymous client is told, and it is told nothing else."""
    response = api_client.get("/api/v1/setup/status")

    assert response.status_code == 200
    assert response.json() == {"needs_setup": True}


def test_a_configured_installation_says_so(api_client: TestClient, generate_user) -> None:
    generate_user()

    assert api_client.get("/api/v1/setup/status").json() == {"needs_setup": False}


# ==========================================
# CREATING THE FIRST ADMINISTRATOR
# ==========================================


def test_the_first_account_is_created_as_an_administrator(api_client: TestClient) -> None:
    response = _create(api_client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert body["name"] == NAME
    assert body["role"] == "ADMIN"
    assert body["is_active"] is True


def test_the_account_does_not_owe_a_password_change(api_client: TestClient) -> None:
    """
    The flag exists because the CLI *generated* the password it printed. Here the person chose it, so
    the installation must not immediately demand it be replaced.
    """
    assert _create(api_client).json()["must_change_password"] is False


def test_the_route_signs_the_person_in(api_client: TestClient) -> None:
    """The account is handed back with a session cookie, so the shell can be drawn without a round trip."""
    response = _create(api_client)

    assert "scrinalia_session=" in response.headers["set-cookie"]
    assert api_client.get("/api/v1/auth/me").json()["email"] == EMAIL


def test_the_answer_never_carries_the_password_or_its_hash(api_client: TestClient) -> None:
    body = _create(api_client).text

    assert PASSWORD not in body
    assert "argon2" not in body
    assert "password_hash" not in body


def test_the_client_cannot_choose_the_role(api_client: TestClient) -> None:
    """The first account administers. A ``role`` in the body is not a field of the command at all."""
    response = _create(api_client, role="VIEWER")

    assert response.status_code == 201
    assert response.json()["role"] == "ADMIN"


def test_the_address_is_stored_normalised(api_client: TestClient) -> None:
    response = _create(api_client, email="  ANA@Instituicao.ORG ")

    assert response.json()["email"] == EMAIL


# ==========================================
# THE DOOR CLOSING
# ==========================================


def test_the_second_call_is_refused(api_client: TestClient) -> None:
    assert _create(api_client).status_code == 201

    refusal = _create(api_client, email="outra@instituicao.org")

    assert refusal.status_code == 409
    assert refusal.json()["error_code"] == "SetupAlreadyCompleteError"


def test_any_existing_account_closes_the_route(api_client: TestClient, generate_user) -> None:
    """
    The predicate is "``auth_users`` is empty", not "has an administrator".

    A deactivated viewer is enough to say the installation has been configured; a rule that a
    deactivation could reopen would be a way back to the open door (ADR 0011).
    """
    generate_user(email="ninguem@instituicao.org", role=Role.VIEWER, is_active=False)

    # Read first: a request that *raises* rolls the shared test transaction back to its savepoint,
    # which would take this uncommitted fixture row with it.
    assert api_client.get("/api/v1/setup/status").json() == {"needs_setup": False}

    response = _create(api_client)

    assert response.status_code == 409


# ==========================================
# WHAT IS REFUSED BEFORE ANYTHING IS WRITTEN
# ==========================================


def test_a_password_below_the_policy_is_refused(api_client: TestClient) -> None:
    response = _create(api_client, password="curta")

    assert response.status_code == 422
    assert response.json()["error_code"] == "WeakPasswordError"


def test_a_malformed_address_is_refused(api_client: TestClient) -> None:
    response = _create(api_client, email="sem-arroba")

    assert response.status_code == 422
    assert response.json()["error_code"] == "InvalidEmailError"


def test_a_refused_payload_leaves_the_installation_empty(api_client: TestClient) -> None:
    """A rejected attempt must not close the route: nothing was written, so nothing is configured."""
    _create(api_client, password="curta")

    assert api_client.get("/api/v1/setup/status").json() == {"needs_setup": True}
    assert _create(api_client).status_code == 201

"""Account administration as HTTP: who may reach it, what the payloads look like, and the two
refusals that only the route layer can get wrong.

The service's rules — the last-admin guard, the password policy, the session bookkeeping — are
asserted against the database in ``testing/integration/identity``. What is asserted here is the part
only HTTP owns: the permission gate, the status of each outcome, the shape of the answer, and the
``is_current`` flag the controller derives from the cookie.
"""

from litestar.testing import TestClient

from scrinalia.domains.identity.domain.permissions import Role

PASSWORD = "uma senha bem longa"
NEW_PASSWORD = "uma senha ainda mais longa"


def _create(client: TestClient, **overrides):
    body = {
        "email": "ana@arquivo.org",
        "name": "Ana",
        "role": "CURATOR",
        "password": PASSWORD,
    }
    body.update(overrides)
    return client.post("/api/v1/users", json=body)


# ==========================================
# WHO MAY REACH THE ACCOUNTS
# ==========================================


def test_the_accounts_require_a_session(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/users").status_code == 401


def test_a_curator_cannot_administer_accounts(sign_in) -> None:
    """The screen that manages accounts is the surface of ``Permission.ADMIN`` and of nothing else."""
    curator = sign_in(Role.CURATOR)

    assert curator.get("/api/v1/users").status_code == 403
    assert _create(curator).status_code == 403


def test_a_viewer_cannot_administer_accounts(sign_in) -> None:
    viewer = sign_in(Role.VIEWER)

    assert viewer.get("/api/v1/users").status_code == 403
    assert viewer.delete("/api/v1/users/1/sessions").status_code == 403


# ==========================================
# READING AND CREATING
# ==========================================


def test_an_administrator_lists_every_account_including_the_closed_ones(client: TestClient, generate_user) -> None:
    """A deactivated account is exactly what explains why somebody cannot sign in; hiding it is a lie."""
    generate_user(email="ana@arquivo.org", name="Ana", role=Role.CURATOR)
    generate_user(email="bruno@arquivo.org", name="Bruno", role=Role.VIEWER, is_active=False)

    body = client.get("/api/v1/users").json()

    by_email = {row["email"]: row for row in body}
    assert by_email["ana@arquivo.org"]["is_active"] is True
    assert by_email["bruno@arquivo.org"]["is_active"] is False


def test_the_list_never_carries_a_password_or_its_hash(client: TestClient) -> None:
    text = client.get("/api/v1/users").text

    assert "argon2" not in text
    assert "password_hash" not in text


def test_creating_an_account_hands_back_the_row_and_a_temporary_password(client: TestClient) -> None:
    """
    The administrator typed the password, so the account has to replace it at the first sign-in —
    otherwise the bootstrap password of one person becomes the permanent credential of another.
    """
    response = _create(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@arquivo.org"
    assert body["role"] == "CURATOR"
    assert body["must_change_password"] is True
    assert PASSWORD not in response.text

    sign_in = client.post("/api/v1/auth/login", json={"email": "ana@arquivo.org", "password": PASSWORD})
    assert sign_in.status_code == 200
    assert sign_in.json()["must_change_password"] is True


def test_a_taken_address_is_a_conflict(client: TestClient, generate_user) -> None:
    generate_user(email="ana@arquivo.org")

    response = _create(client)

    assert response.status_code == 409
    assert response.json()["error_code"] == "DuplicateUserEmailError"


def test_a_weak_password_is_refused_by_the_domain_policy(client: TestClient) -> None:
    response = _create(client, password="curta")

    assert response.status_code == 422
    assert response.json()["error_code"] == "WeakPasswordError"


# ==========================================
# EDITING, RESETTING AND DEACTIVATING
# ==========================================


def test_an_administrator_changes_the_role_and_the_name(client: TestClient, generate_user) -> None:
    ana = generate_user(email="ana@arquivo.org", name="Ana", role=Role.CURATOR)

    response = client.patch(f"/api/v1/users/{ana.user_id}", json={"name": "Ana Maria", "role": "VIEWER"})

    assert response.status_code == 200
    assert response.json()["name"] == "Ana Maria"
    assert response.json()["role"] == "VIEWER"


def test_deactivating_the_last_administrator_is_refused(client: TestClient) -> None:
    """
    The only lockout with no way back through the screen.

    The account here is the one making the request, which is the shape the trap actually takes: an
    administrator closing their own account.
    """
    me = client.get("/api/v1/auth/me").json()

    response = client.patch(f"/api/v1/users/{me['user_id']}", json={"is_active": False})

    assert response.status_code == 409
    assert response.json()["error_code"] == "LastAdminError"


def test_resetting_a_password_answers_a_code_and_ends_the_old_password(client: TestClient, generate_user) -> None:
    ana = generate_user(email="ana@arquivo.org", password=PASSWORD)

    response = client.post(f"/api/v1/users/{ana.user_id}/password", json={"password": NEW_PASSWORD})

    assert response.status_code == 200
    assert response.json()["code"] == "USER_PASSWORD_RESET"
    assert client.post("/api/v1/auth/login", json={"email": "ana@arquivo.org", "password": PASSWORD}).status_code == 401
    assert (
        client.post("/api/v1/auth/login", json={"email": "ana@arquivo.org", "password": NEW_PASSWORD}).status_code
        == 200
    )


def test_an_unknown_account_is_a_not_found(client: TestClient) -> None:
    assert client.patch("/api/v1/users/999", json={"name": "Ninguém"}).status_code == 404
    assert client.get("/api/v1/users/999/sessions").status_code == 404
    assert client.post("/api/v1/users/999/password", json={"password": NEW_PASSWORD}).status_code == 404


# ==========================================
# THE SESSIONS OF AN ACCOUNT
# ==========================================


def test_the_session_making_the_request_is_marked(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()

    rows = client.get(f"/api/v1/users/{me['user_id']}/sessions").json()

    assert len(rows) == 1
    assert rows[0]["is_current"] is True


def test_an_administrator_lists_and_revokes_a_session_of_another_account(
    client: TestClient, generate_user, auth_service
) -> None:
    ana = generate_user(email="ana@arquivo.org", password=PASSWORD)
    token, _ = auth_service.login("ana@arquivo.org", PASSWORD)

    listed = client.get(f"/api/v1/users/{ana.user_id}/sessions")

    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    # Not the administrator's own cookie: the flag is about this request, not about the account.
    assert rows[0]["is_current"] is False

    revoked = client.delete(f"/api/v1/users/{ana.user_id}/sessions/{rows[0]['session_id']}")

    assert revoked.status_code == 200
    assert revoked.json()["code"] == "SESSION_REVOKED"
    assert auth_service.resolve_session(token) is None


def test_an_administrator_ends_every_session_of_an_account(client: TestClient, generate_user, auth_service) -> None:
    ana = generate_user(email="ana@arquivo.org", password=PASSWORD)
    tokens = [auth_service.login("ana@arquivo.org", PASSWORD)[0] for _ in range(2)]

    response = client.delete(f"/api/v1/users/{ana.user_id}/sessions")

    assert response.status_code == 200
    assert response.json()["code"] == "USER_SESSIONS_REVOKED"
    assert all(auth_service.resolve_session(token) is None for token in tokens)


def test_a_session_id_of_another_account_is_not_found(client: TestClient, generate_user, auth_service) -> None:
    """
    The id alone is not enough, and the answer is 404 and not 200: confirming that a session id
    exists under a different account would enumerate other people's sign-ins.
    """
    ana = generate_user(email="ana@arquivo.org", password=PASSWORD)
    bruno = generate_user(email="bruno@arquivo.org", password=PASSWORD)
    token, _ = auth_service.login("ana@arquivo.org", PASSWORD)
    session = auth_service.list_sessions(ana.user_id)[0]

    response = client.delete(f"/api/v1/users/{bruno.user_id}/sessions/{session.session_id}")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SessionNotFoundError"
    assert auth_service.resolve_session(token) is not None

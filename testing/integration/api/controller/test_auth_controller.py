"""The session routes as HTTP: the cookie, the two refusals that must be indistinguishable, and the
account's own password.

The service's rules are tested against the database in ``testing/integration/identity``. What is
asserted here is the part only HTTP can get wrong: what lands in the cookie, what the body says, and
whether an anonymous client is told apart from one whose password was wrong.
"""

from litestar.testing import TestClient

from scrinalia.domains.identity.domain.permissions import Role

EMAIL = "maria@teste.local"
PASSWORD = "uma senha bem longa"
NEW_PASSWORD = "uma senha ainda mais longa"


def _login(client: TestClient, *, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# ==========================================
# SIGNING IN
# ==========================================


def test_login_hands_back_the_account_and_a_cookie(api_client: TestClient, generate_user) -> None:
    generate_user(email=EMAIL, name="Maria", role=Role.CURATOR, password=PASSWORD)

    response = _login(api_client)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == EMAIL
    assert body["role"] == "CURATOR"
    assert "scrinalia_session=" in response.headers["set-cookie"]


def test_the_answer_never_carries_the_password_or_its_hash(api_client: TestClient, generate_user) -> None:
    """
    The login answer is the account, and the account has no password field to forget to exclude.

    Asserted on the raw text and not on the model: a field added to the DTO by mistake would show up
    here even if the model is not what the client reads.
    """
    generate_user(email=EMAIL, password=PASSWORD)

    body = _login(api_client).text

    assert PASSWORD not in body
    assert "argon2" not in body
    assert "password_hash" not in body


def test_a_wrong_password_is_a_401(api_client: TestClient, generate_user) -> None:
    generate_user(email=EMAIL, password=PASSWORD)

    response = _login(api_client, password="a senha errada")

    assert response.status_code == 401
    assert response.json()["error_code"] == "InvalidCredentialsError"


def test_an_unknown_address_answers_exactly_like_a_wrong_password(api_client: TestClient, generate_user) -> None:
    """
    The enumeration guard at the boundary.

    Status *and* sentence are compared: a different wording is the same oracle as a different code,
    and this is the answer an anonymous caller can get as many times as they like.
    """
    generate_user(email=EMAIL, password=PASSWORD)

    unknown = _login(api_client, email="ninguem@teste.local")
    wrong = _login(api_client, password="a senha errada")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_a_deactivated_account_answers_like_an_unknown_one(api_client: TestClient, generate_user) -> None:
    generate_user(email=EMAIL, password=PASSWORD, is_active=False)

    deactivated = _login(api_client)
    unknown = _login(api_client, email="ninguem@teste.local")

    assert deactivated.status_code == 401
    assert deactivated.json() == unknown.json()


# ==========================================
# KEEPING AND ENDING A SESSION
# ==========================================


def test_me_describes_the_account_behind_the_session(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "admin@teste.local"
    assert response.json()["role"] == "ADMIN"


def test_me_without_a_session_is_a_401(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/auth/me").status_code == 401


def test_logout_ends_the_session_and_clears_the_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert response.json()["code"] == "SESSION_ENDED"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_without_a_session_is_a_401(api_client: TestClient) -> None:
    """
    Ending a session requires having one.

    The alternative — declaring ``logout`` public so it can always clear the cookie — would let any
    page sign the archivist out with a cross-site form post. A dead cookie left in the browser is
    harmless: the session behind it is already over.
    """
    assert api_client.post("/api/v1/auth/logout").status_code == 401


# ==========================================
# THE ACCOUNT'S OWN PASSWORD
# ==========================================


def test_the_password_can_be_changed_knowing_the_current_one(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": "senha de teste bem longa", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "PASSWORD_CHANGED"
    # The session that made the change survives it: being logged out of the screen you are on is not
    # what somebody securing their account asked for.
    assert client.get("/api/v1/auth/me").status_code == 200


def test_the_old_password_stops_working_after_the_change(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/password",
        json={"current_password": "senha de teste bem longa", "new_password": NEW_PASSWORD},
    )
    client.post("/api/v1/auth/logout")

    assert _login(client, email="admin@teste.local", password="senha de teste bem longa").status_code == 401
    assert _login(client, email="admin@teste.local", password=NEW_PASSWORD).status_code == 200


def test_a_wrong_current_password_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": "a senha errada", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "InvalidCurrentPasswordError"


def test_a_new_password_below_the_policy_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": "senha de teste bem longa", "new_password": "curta"},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "WeakPasswordError"

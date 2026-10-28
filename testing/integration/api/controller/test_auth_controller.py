"""The session routes as HTTP: the cookie, the two refusals that must be indistinguishable, and the
account's own password.

The service's rules are tested against the database in ``testing/integration/identity``. What is
asserted here is the part only HTTP can get wrong: what lands in the cookie, what the body says, and
whether an anonymous client is told apart from one whose password was wrong.
"""

from litestar.testing import TestClient

from scrinalia.core.config import settings
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


# ==========================================
# THE TEMPORARY PASSWORD IS NOT A CREDENTIAL (issue #79)
# ==========================================


def _sign_in_owing_a_password_change(api_client: TestClient, generate_user) -> TestClient:
    """An account the CLI or an administrator created, signed in with the password it printed."""
    generate_user(email=EMAIL, name="Maria", role=Role.CURATOR, password=PASSWORD, must_change_password=True)
    assert _login(api_client).status_code == 200
    return api_client


def test_the_temporary_password_reaches_only_the_change_itself(api_client: TestClient, generate_user) -> None:
    """
    The flag is enforced by the API, not by the screen.

    Until the temporary password is replaced, the account's whole role is refused on every ordinary
    operation — reading included, because the read is the reconnaissance the flag exists to stop.
    """
    signed_in = _sign_in_owing_a_password_change(api_client, generate_user)

    refused = signed_in.get("/api/v1/curation/inbox")

    assert refused.status_code == 403
    body = refused.json()
    assert body["error_code"] == "PasswordChangeRequiredException"
    assert body["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert body["message"]


def test_the_forced_change_still_reaches_the_routes_it_needs(api_client: TestClient, generate_user) -> None:
    """
    The three ways out the forced screen stands on: read the session, end it, replace the password.

    ``/auth/me`` and ``/auth/logout`` are exempt because a screen that cannot read its own session or
    sign out is a trap; ``/auth/password`` is the change itself.
    """
    signed_in = _sign_in_owing_a_password_change(api_client, generate_user)

    assert signed_in.get("/api/v1/auth/me").status_code == 200
    assert signed_in.post("/api/v1/auth/logout").status_code == 200


def test_replacing_the_password_opens_the_rest_of_the_api(api_client: TestClient, generate_user) -> None:
    signed_in = _sign_in_owing_a_password_change(api_client, generate_user)

    changed = signed_in.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert changed.status_code == 200
    assert changed.json()["code"] == "PASSWORD_CHANGED"
    # The same request that was refused a moment ago now answers: it is the flag, not the role.
    assert signed_in.get("/api/v1/curation/inbox").status_code == 200


# ==========================================
# THE HARDENING (B9.3)
# ==========================================


def test_repeated_failures_lock_the_account_even_though_every_request_rolled_back(
    api_client: TestClient, generate_user, monkeypatch
) -> None:
    """
    The measured trap, at the boundary where it bites.

    A failed login raises, ``provide_unit_of_work`` rolls the request back, and the counter has to
    survive anyway — that is why it is written through its own committed session. If it were written
    in the request transaction, this test would answer 401 on the last call: the lock would have been
    erased by each failure that created it.
    """
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 3)
    generate_user(email=EMAIL, password=PASSWORD)

    for _ in range(3):
        assert _login(api_client, password="a senha errada").status_code == 401

    locked = _login(api_client)

    assert locked.status_code == 423
    assert locked.json()["error_code"] == "AccountLockedError"


def test_the_lockout_is_visible_on_the_account_the_administrator_reads(
    client: TestClient, generate_user, monkeypatch
) -> None:
    """The lockout is a fact about the account, so the accounts screen has to be able to show it."""
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)
    maria = generate_user(email=EMAIL, password=PASSWORD)
    for _ in range(2):
        _login(client, password="a senha errada")

    body = client.get("/api/v1/users").json()
    row = next(item for item in body if item["user_id"] == maria.user_id)

    assert row["failed_attempts"] == 2
    assert row["locked_until"] is not None


def test_too_many_attempts_from_one_address_answer_429(api_client: TestClient, generate_user, monkeypatch) -> None:
    """The brake in front of the lockout: it counts attempts, not accounts."""
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_MAX", 2)
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_WINDOW_SECONDS", 300)
    generate_user(email=EMAIL, password=PASSWORD)

    assert _login(api_client, password="a senha errada").status_code == 401
    assert _login(api_client, password="a senha errada").status_code == 401

    refused = _login(api_client)

    assert refused.status_code == 429
    assert refused.json()["error_code"] == "TooManyLoginAttemptsError"


# ==========================================
# THE ACCOUNT'S LANGUAGE (ADR 0020 §3)
# ==========================================


def test_the_account_stores_the_interface_language(api_client: TestClient, generate_user) -> None:
    """The choice is stored on the account, so it follows the person and not the browser."""
    generate_user(email=EMAIL, password=PASSWORD)
    _login(api_client)

    response = api_client.patch("/api/v1/auth/me", json={"locale": "en"})

    assert response.status_code == 200
    assert response.json()["locale"] == "en"
    assert api_client.get("/api/v1/auth/me").json()["locale"] == "en"


def test_automatic_clears_the_language(api_client: TestClient, generate_user) -> None:
    """``null`` is a choice: automatic means the SPA follows the browser again."""
    generate_user(email=EMAIL, password=PASSWORD)
    _login(api_client)
    api_client.patch("/api/v1/auth/me", json={"locale": "en"})

    response = api_client.patch("/api/v1/auth/me", json={"locale": None})

    assert response.status_code == 200
    assert response.json()["locale"] is None


def test_an_unknown_language_is_refused(api_client: TestClient, generate_user) -> None:
    generate_user(email=EMAIL, password=PASSWORD)
    _login(api_client)

    response = api_client.patch("/api/v1/auth/me", json={"locale": "fr"})

    # Litestar answers a malformed body with 400; 422 is the domain's refusal, not the schema's.
    assert response.status_code == 400


def test_the_language_needs_a_session(api_client: TestClient) -> None:
    response = api_client.patch("/api/v1/auth/me", json={"locale": "en"})

    assert response.status_code == 401


def test_logout_answers_in_the_requested_language(api_client: TestClient, generate_user) -> None:
    """The sentence a screen shows is composed in the language of the request (ADR 0020 §4)."""
    generate_user(email=EMAIL, password=PASSWORD)
    _login(api_client)

    english = api_client.post("/api/v1/auth/logout", headers={"Accept-Language": "en-US"})
    assert english.json()["message"] == "Signed out."

    _login(api_client)
    portuguese = api_client.post("/api/v1/auth/logout", headers={"Accept-Language": "pt-BR"})
    assert portuguese.json()["message"] == "Sessão encerrada."

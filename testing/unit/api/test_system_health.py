"""The probes must degrade one at a time, and never leak a secret.

A monitoring screen that turns a dead database into a 500 is useless exactly when it is needed, so
every probe answers on its own. And a screen that prints the credentials it was asked to check is a
security incident, so the process probe reports presence, not content.
"""

import sys

from botocore.exceptions import ClientError
from pydantic import SecretStr

from scrinalia.api import system_health


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_ollama_probe_reports_the_missing_models(monkeypatch) -> None:
    monkeypatch.setattr(system_health.settings, "OLLAMA_HOST_URL", "http://ollama.interno:11434")
    monkeypatch.setattr(
        system_health.requests,
        "get",
        lambda url, timeout: _Response({"models": [{"name": "granite4.1:3b"}]}),
    )

    health = system_health.probe_ollama()

    assert health.ok is True
    assert health.host == "http://ollama.interno:11434"
    assert health.host_source == "OLLAMA_HOST_URL"
    assert "granite4.1:3b" in health.installed_models
    assert "gemma4:e4b" in health.missing_models


def test_a_retired_preset_is_not_a_required_model() -> None:
    """
    #122: the health probe compares what the **presets** name against what the server has, so a
    preset that retired stops being demanded. ``granite4.1:3b`` is installed here and still cannot
    run; the probe must not keep the panel asking for it.
    """
    required = system_health.required_ollama_models()

    assert "gemma4:e4b" in required
    assert "granite4.1:3b" not in required


def test_ollama_probe_survives_the_server_being_down(monkeypatch) -> None:
    def explode(url, timeout):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(system_health.requests, "get", explode)

    health = system_health.probe_ollama()

    assert health.ok is False
    assert "connection refused" in (health.detail or "")
    # The required models are still reported: that is what the screen needs to say.
    assert health.required_models


def test_storage_probe_says_it_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(system_health.settings, "S3_ENDPOINT_URL", None)
    monkeypatch.setattr(system_health.settings, "S3_BUCKET_NAME", None)

    health = system_health.probe_storage()

    assert health.configured is False
    assert health.ok is False
    assert "não configurado" in (health.detail or "")
    # The detail names what is missing, from the same predicate the reader uses, instead of a
    # generic "endpoint, bucket or credentials" that could hide an empty credential (#258).
    assert "S3_ENDPOINT_URL" in (health.detail or "")
    assert "S3_BUCKET_NAME" in (health.detail or "")


def test_storage_probe_reports_a_bucket_that_does_not_answer(monkeypatch) -> None:
    monkeypatch.setattr(system_health.settings, "S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setattr(system_health.settings, "S3_BUCKET_NAME", "bronze")
    # The credentials are part of what "configured" means, and the probe reads them from the settings
    # object. Without setting them here the test passes only on a machine whose `.env` happens to
    # carry them, which is exactly how it passed locally and failed on the first CI run.
    monkeypatch.setattr(system_health.settings, "S3_ACCESS_KEY", SecretStr("chave"))
    monkeypatch.setattr(system_health.settings, "S3_SECRET_KEY", SecretStr("segredo"))

    class _BrokenClient:
        def head_bucket(self, Bucket):  # the boto3 signature is capitalised
            raise RuntimeError("NoSuchBucket")

    class _BrokenBoto3:
        @staticmethod
        def client(*args, **kwargs):
            return _BrokenClient()

    monkeypatch.setitem(sys.modules, "boto3", _BrokenBoto3)

    health = system_health.probe_storage()

    assert health.configured is True
    assert health.ok is False
    assert "NoSuchBucket" in (health.detail or "")


def _configured_storage(monkeypatch, *, auto_create: bool) -> None:
    monkeypatch.setattr(system_health.settings, "S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setattr(system_health.settings, "S3_BUCKET_NAME", "bronze")
    monkeypatch.setattr(system_health.settings, "S3_ACCESS_KEY", SecretStr("chave"))
    monkeypatch.setattr(system_health.settings, "S3_SECRET_KEY", SecretStr("segredo"))
    monkeypatch.setattr(system_health.settings, "S3_AUTO_CREATE_BUCKET", auto_create)


def _install_s3_client(monkeypatch, client) -> None:
    class _Boto3:
        @staticmethod
        def client(*args, **kwargs):
            return client

    monkeypatch.setitem(sys.modules, "boto3", _Boto3)


class _MissingBucketClient:
    """The endpoint answering ``404`` on the HEAD — what SeaweedFS does for a bucket not created."""

    def head_bucket(self, Bucket):
        raise ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadBucket")


def test_storage_probe_names_a_missing_bucket_instead_of_a_permission_error(monkeypatch) -> None:
    """With auto-create off, "down" has to say *which* piece is missing and how to create it."""
    _configured_storage(monkeypatch, auto_create=False)
    _install_s3_client(monkeypatch, _MissingBucketClient())

    health = system_health.probe_storage()

    assert health.configured is True
    assert health.ok is False
    assert "não existe" in (health.detail or "")
    assert "S3_AUTO_CREATE_BUCKET=true" in (health.detail or "")


def test_storage_probe_reports_up_when_the_worker_will_create_the_bucket(monkeypatch) -> None:
    """The probe never creates — a GET that provisions is a write hiding in a read — but it must not
    call the endpoint down when the worker is allowed to provision it on the first upload."""
    _configured_storage(monkeypatch, auto_create=True)
    _install_s3_client(monkeypatch, _MissingBucketClient())

    health = system_health.probe_storage()

    assert health.ok is True
    assert "S3_AUTO_CREATE_BUCKET=true" in (health.detail or "")


def test_the_database_probe_answers_instead_of_raising(monkeypatch) -> None:
    def explode():
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(system_health, "create_session", explode)

    health = system_health.probe_database()

    assert health.ok is False
    assert "banco fora do ar" in (health.detail or "")


def test_the_process_probe_never_reveals_a_secret(monkeypatch) -> None:
    monkeypatch.setattr(system_health.settings, "DB_PASS", SecretStr("segredo-do-banco"))

    health = system_health.probe_process()
    payload = health.model_dump()

    assert payload["secrets_present"]["DB_PASS"] is True
    serialized = str(payload)
    assert "segredo-do-banco" not in serialized
    assert "admin123" not in serialized


class _FakeScalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def scalars(self, _statement: object) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeOrigin:
    def __init__(self, code: str, enabled: bool) -> None:
        self.code = code
        self.enabled = enabled


def test_the_ingestion_probe_counts_only_the_sources(monkeypatch) -> None:
    """The probe counts what the origins page manages, and nothing else (#206).

    The manual and CSV entries keep their rows for provenance and the retired code stays readable in
    the table, but none of them is a source the page configures: counting them would make "N de M
    origens ativas" disagree with the page it describes.
    """
    rows = [
        _FakeOrigin("manual", enabled=False),
        _FakeOrigin("csv", enabled=True),
        _FakeOrigin("pmc", enabled=True),
        _FakeOrigin("retired", enabled=True),
    ]
    monkeypatch.setattr(system_health, "create_session", lambda: _FakeSession(rows))

    health = system_health.probe_ingestion()

    assert health.ok is True
    assert (health.total, health.enabled) == (1, 1)
    assert [origin.code for origin in health.origins] == ["pmc"]
    assert health.origins[0].label == "Acervo de referência (PMC)"


def test_the_ingestion_probe_answers_instead_of_raising(monkeypatch) -> None:
    def explode():
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(system_health, "create_session", explode)

    health = system_health.probe_ingestion()

    assert health.ok is False
    assert "banco fora do ar" in (health.detail or "")

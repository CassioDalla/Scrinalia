"""The probes must degrade one at a time, and never leak a secret.

A monitoring screen that turns a dead database into a 500 is useless exactly when it is needed, so
every probe answers on its own. And a screen that prints the credentials it was asked to check is a
security incident, so the process probe reports presence, not content.
"""

import sys

from pydantic import SecretStr

from memoria_curitibana.api import system_health


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


def test_storage_probe_reports_a_bucket_that_does_not_answer(monkeypatch) -> None:
    monkeypatch.setattr(system_health.settings, "S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setattr(system_health.settings, "S3_BUCKET_NAME", "bronze")

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

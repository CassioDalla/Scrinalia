"""The cross-origin decision on mutations, as a pure function.

Two ways to be allowed and no third: the origin is one the deployment declared, or its authority is
the one the request was addressed to. The guard around this is exercised through HTTP in
``testing/integration/api/controller/test_auth_controller.py``; what is pinned here is the comparison
itself, including the cases that must *not* be allowed.
"""

from scrinalia.api.security import is_allowed_origin


def test_the_host_the_request_was_addressed_to_is_allowed() -> None:
    assert is_allowed_origin("http://arquivo.org", "arquivo.org", set()) is True


def test_a_spelled_out_default_port_is_the_same_place() -> None:
    assert is_allowed_origin("https://arquivo.org:443", "arquivo.org", set()) is True
    assert is_allowed_origin("http://arquivo.org", "arquivo.org:80", set()) is True


def test_a_non_default_port_must_match() -> None:
    assert is_allowed_origin("http://localhost:5173", "localhost:5173", set()) is True
    assert is_allowed_origin("http://localhost:5173", "localhost:8000", set()) is False


def test_a_configured_origin_is_allowed_even_when_the_host_differs() -> None:
    """The reverse-proxy case: the public origin is not the internal Host the app receives."""
    trusted = {"https://curador.arquivo.org"}

    assert is_allowed_origin("https://curador.arquivo.org", "interno:8000", trusted) is True


def test_another_host_is_refused() -> None:
    assert is_allowed_origin("https://evil.example", "arquivo.org", set()) is False


def test_an_opaque_or_malformed_origin_is_refused() -> None:
    assert is_allowed_origin("null", "arquivo.org", set()) is False
    assert is_allowed_origin("", "arquivo.org", set()) is False
    # A bare host is not an origin: without a scheme there is nothing to compare.
    assert is_allowed_origin("arquivo.org", "arquivo.org", set()) is False


def test_case_and_a_trailing_slash_do_not_change_the_verdict() -> None:
    assert is_allowed_origin("HTTP://Arquivo.ORG/", "arquivo.org", set()) is True

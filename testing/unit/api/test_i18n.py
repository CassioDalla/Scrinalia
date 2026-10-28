"""The request's language, from the header the client sends."""

from scrinalia.api.i18n import negotiate_locale
from scrinalia.core.locale import Locale


def test_a_missing_header_gets_the_product_language() -> None:
    assert negotiate_locale(None) is Locale.PT_BR


def test_the_supported_tags_win_by_quality() -> None:
    assert negotiate_locale("en-US") is Locale.EN
    assert negotiate_locale("pt-PT") is Locale.PT_BR
    assert negotiate_locale("pt-BR,pt;q=0.9,en;q=0.8") is Locale.PT_BR
    assert negotiate_locale("en;q=0.2,pt;q=0.9") is Locale.PT_BR
    assert negotiate_locale("de-DE,en;q=0.8") is Locale.EN


def test_an_unsupported_or_absent_language_falls_back() -> None:
    assert negotiate_locale("fr-FR") is Locale.PT_BR
    assert negotiate_locale("en;q=0") is Locale.PT_BR
    assert negotiate_locale("") is Locale.PT_BR

"""
Which language the deployment speaks, resolved once.

``ACERVO_LANGUAGE`` selects the profile; ``pt-BR`` is the default because it is the
language the reference collection is in, not because the system requires it. The lookup
fails fast on an unknown tag: a typo in the environment must not silently fall back to a
profile the operator did not choose, which would mix languages in one installation.
"""

from functools import lru_cache

from scrinalia.core.config import settings
from scrinalia.core.language.base import LanguageProfile
from scrinalia.core.language.pt_br import PT_BR

#: Every profile the package ships. Adding a language is adding an entry here and a module.
LANGUAGES: dict[str, LanguageProfile] = {PT_BR.code: PT_BR}

#: The profile used when ``ACERVO_LANGUAGE`` is unset.
DEFAULT_LANGUAGE = PT_BR.code


@lru_cache
def get_language(code: str | None = None) -> LanguageProfile:
    """
    The active profile: the explicit tag wins, then ``ACERVO_LANGUAGE``, then ``pt-BR``.

    Cached because it is a constant of the process and every guard and parser call reads it.
    Tests isolate it with ``get_language.cache_clear()``, exactly like ``get_settings``.
    """
    resolved = code or settings.ACERVO_LANGUAGE or DEFAULT_LANGUAGE
    try:
        return LANGUAGES[resolved]
    except KeyError:
        raise ValueError(f"Unknown language {resolved!r}. Available: {sorted(LANGUAGES)}") from None

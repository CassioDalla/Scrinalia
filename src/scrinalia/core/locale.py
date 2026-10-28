"""The locales the interface speaks (ADR 0020).

One definition for both sides: the account column, the request header the API negotiates from and
the catalogue it renders sentences with all speak these two values.
"""

import enum


class Locale(enum.StrEnum):
    """A language the interface can be read in."""

    PT_BR = "pt-BR"
    EN = "en"


#: What a request without a usable ``Accept-Language`` gets: the product's own language.
DEFAULT_LOCALE = Locale.PT_BR

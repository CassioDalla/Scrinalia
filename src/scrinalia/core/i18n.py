"""The request's language, and the sentences a refusal is written in (ADR 0020 §4).

The locale rides in a ``ContextVar`` because refusals are raised in services and guards as well as in
controllers, and threading a ``Request`` through those layers would make the domain know HTTP. The
middleware in ``api/i18n.py`` binds it per request; outside a request — the CLI, a worker — it stays
at the product's language.

A refusal is a **code plus facts**, not a sentence composed at the raise site in one language: the
catalogue holds the two texts and the facts travel as named values, so the English never has to parse
the Portuguese. :func:`refusal` raises ``KeyError`` for a code with no entry, which is the loud
failure a forgotten translation deserves.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from scrinalia.core.locale import DEFAULT_LOCALE, Locale

_current: ContextVar[Locale] = ContextVar("scrinalia_locale", default=DEFAULT_LOCALE)


def negotiate_locale(header: str | None) -> Locale:
    """
    The best supported language of an ``Accept-Language`` header.

    The header is a list of tags with optional ``q`` weights; the highest one this API speaks wins,
    and anything else falls back to ``pt-BR`` — the product's language, which is also what a client
    that sends no header has always received. ``q=0`` means "not acceptable" and is skipped.
    """
    if not header:
        return DEFAULT_LOCALE

    candidates: list[tuple[float, str]] = []
    for part in header.split(","):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip().lower()
        if not tag:
            continue
        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality > 0:
            candidates.append((quality, tag))

    for _, tag in sorted(candidates, key=lambda item: item[0], reverse=True):
        if tag.startswith("pt"):
            return Locale.PT_BR
        if tag.startswith("en"):
            return Locale.EN
    return DEFAULT_LOCALE


def current_locale() -> Locale:
    """The language of the request being served."""
    return _current.get()


def bind_locale(header: str | None) -> Token[Locale]:
    """Binds the header's language for the rest of the request; the caller resets the token."""
    return _current.set(negotiate_locale(header))


def reset_locale(token: Token[Locale]) -> None:
    _current.reset(token)


#: The refusal catalogue: one stable code, one sentence per language, facts as ``{name}``.
#:
#: The codes are grouped by the area that refuses — ``auth``, ``security`` — and never change once
#: released, exactly like ``RouteMessageCode``. A raise site names the code and passes the facts; it
#: never holds a sentence, so there is one definition per language and no f-string to translate.
REFUSALS: dict[str, dict[Locale, str]] = {
    # --- Identity: signing in and the account ------------------------------------------------
    "auth.invalid_credentials": {
        Locale.PT_BR: "E-mail ou senha inválidos.",
        Locale.EN: "Invalid e-mail or password.",
    },
    "auth.account_locked": {
        Locale.PT_BR: (
            "Conta temporariamente bloqueada por tentativas de acesso. Tente novamente mais tarde "
            "ou peça ao administrador uma nova senha."
        ),
        Locale.EN: (
            "Account temporarily locked after sign-in attempts. Try again later "
            "or ask the administrator for a new password."
        ),
    },
    "auth.setup_complete": {
        Locale.PT_BR: (
            "Esta instalação já tem uma conta. O primeiro acesso só pode ser criado uma vez; "
            "peça a quem administra que crie a sua conta."
        ),
        Locale.EN: (
            "This installation already has an account. First access can only be created once; "
            "ask whoever administers it to create your account."
        ),
    },
    "auth.invalid_email": {
        Locale.PT_BR: "Informe um e-mail válido.",
        Locale.EN: "Enter a valid e-mail.",
    },
    "auth.weak_password_min": {
        Locale.PT_BR: "A senha precisa ter ao menos {minimum} caracteres.",
        Locale.EN: "The password needs at least {minimum} characters.",
    },
    "auth.weak_password_email": {
        Locale.PT_BR: "A senha não pode ser o próprio e-mail.",
        Locale.EN: "The password cannot be the e-mail itself.",
    },
    "auth.invalid_current_password": {
        Locale.PT_BR: "A senha atual não confere.",
        Locale.EN: "The current password does not match.",
    },
    "auth.user_not_found": {
        Locale.PT_BR: "Conta {user_id} não encontrada.",
        Locale.EN: "Account {user_id} not found.",
    },
    "auth.session_not_found": {
        Locale.PT_BR: "Sessão {session_id} não encontrada para esta conta.",
        Locale.EN: "Session {session_id} not found for this account.",
    },
    "auth.duplicate_email": {
        Locale.PT_BR: "Já existe uma conta com o e-mail {email}.",
        Locale.EN: "An account with the e-mail {email} already exists.",
    },
    "auth.last_admin": {
        Locale.PT_BR: "Esta é a última conta de administrador ativa; promova outra conta antes de alterar esta.",
        Locale.EN: "This is the last active administrator account; promote another account before changing this one.",
    },
    "auth.too_many_attempts": {
        Locale.PT_BR: "Muitas tentativas de acesso a partir deste endereço. Aguarde alguns minutos.",
        Locale.EN: "Too many sign-in attempts from this address. Wait a few minutes.",
    },
    # --- The access guard --------------------------------------------------------------------
    "security.session_required": {
        Locale.PT_BR: "É preciso entrar para acessar o sistema.",
        Locale.EN: "You must sign in to access the system.",
    },
    "security.permission_denied": {
        Locale.PT_BR: "Sua conta não tem permissão para esta ação.",
        Locale.EN: "Your account does not have permission for this action.",
    },
    "security.unclassified_route": {
        Locale.PT_BR: "Rota sem classificação de acesso.",
        Locale.EN: "Route without an access classification.",
    },
    "security.cross_origin": {
        Locale.PT_BR: "Requisição recusada: a origem não é a deste sistema.",
        Locale.EN: "Request refused: the origin is not this system's.",
    },
    "security.password_change_required": {
        Locale.PT_BR: "Troque a senha temporária antes de usar o sistema.",
        Locale.EN: "Change the temporary password before using the system.",
    },
    # --- The last-resort handlers ------------------------------------------------------------
    "security.integrity_error": {
        Locale.PT_BR: "Conflito estrutural no banco de dados. Operação abortada.",
        Locale.EN: "Structural database conflict. Operation aborted.",
    },
    "security.internal_error": {
        Locale.PT_BR: "Erro interno inesperado. A falha foi registrada e pode ser localizada pela referência.",
        Locale.EN: "Unexpected internal error. The failure was recorded and can be located by the reference.",
    },
}


def refusal(code: str, **facts: object) -> str:
    """The sentence for a refusal code, in the request's language."""
    entry = REFUSALS.get(code)
    if entry is None:
        raise KeyError(f"no refusal message for {code}")
    template = entry[current_locale()]
    return template.format(**facts) if facts else template

"""Account administration from the host: the bootstrap, and the way back in.

Run with ``uv run python -m scrinalia.domains.identity.cli``. It exists because the first account
cannot come from the screen — a route that creates an administrator when no account exists is an open
door whose only defence is a race on the first deploy — and because a forgotten password with every
administrator locked out has to be recoverable by whoever holds the server, not by an e-mail nobody
configured.

It runs on the host, with the same service the API uses, so the rules cannot diverge: the last-admin
guard, the password policy and the session revocation are the *same* code. It is not a second
implementation with fewer checks.

Two things it does that the API deliberately does not: it can print a generated password to the
terminal, and it can name the account it is acting on without being one.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrinalia.core.database import get_db
from scrinalia.core.exceptions import DomainException
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.identity.domain.permissions import Role
from scrinalia.domains.identity.repository.session_repo import SessionRepository
from scrinalia.domains.identity.repository.user_repo import UserRepository
from scrinalia.domains.identity.schemas.user_schema import (
    AuthUserDTO,
    CreateUserCommand,
    UpdateUserCommand,
)
from scrinalia.domains.identity.services.auth_service import AuthService

#: Length of the password the CLI generates when none is given. Above the default policy (12) on
#: purpose: this is the one password that travels through a terminal and a person's clipboard.
GENERATED_PASSWORD_BYTES = 12


def _service(db: Session) -> AuthService:
    return AuthService(UserRepository(db), SessionRepository(db))


def _require_user(service: AuthService, email: str):
    user = service.users.get_by_email(email)
    if user is None:
        raise DomainException(f"Nenhuma conta com o e-mail {email}.")
    return user


def _resolve_password(given: str | None) -> tuple[str, bool]:
    """The password to set, and whether it was generated (i.e. the person must replace it)."""
    if given:
        return given, False
    return secrets.token_urlsafe(GENERATED_PASSWORD_BYTES), True


def _create(args: argparse.Namespace, db: Session) -> int:
    service = _service(db)
    password, generated = _resolve_password(args.password)
    user = service.create_user(
        CreateUserCommand(email=args.email, name=args.name, role=Role(args.role), password=password),
        must_change_password=generated,
    )
    print(f"✅ Conta criada: {user.email} ({user.role})")
    if generated:
        print(f"   Senha temporária: {password}")
        print("   Ela deve ser trocada no primeiro acesso.")
    return 0


def _list(args: argparse.Namespace, db: Session) -> int:
    users = _service(db).list_users()
    if not users:
        print("Nenhuma conta cadastrada.")
        return 0
    print(f"{'ID':>4}  {'E-MAIL':<40} {'PAPEL':<8} {'ATIVA':<6} NOME")
    for user in users:
        dto = AuthUserDTO.model_validate(user)
        print(f"{dto.user_id:>4}  {dto.email:<40} {dto.role:<8} {'sim' if dto.is_active else 'não':<6} {dto.name}")
    return 0


def _reset_password(args: argparse.Namespace, db: Session) -> int:
    service = _service(db)
    user = _require_user(service, args.email)
    password, generated = _resolve_password(args.password)
    service.reset_password(user, password, must_change=generated)
    print(f"✅ Senha redefinida para {user.email}; as sessões abertas foram encerradas.")
    if generated:
        print(f"   Senha temporária: {password}")
        print("   Ela deve ser trocada no primeiro acesso.")
    return 0


def _set_active(args: argparse.Namespace, db: Session) -> int:
    service = _service(db)
    user = _require_user(service, args.email)
    service.update_user(user, UpdateUserCommand(is_active=args.active))
    state = "ativada" if args.active else "desativada"
    print(f"✅ Conta {user.email} {state}.")
    return 0


def _set_role(args: argparse.Namespace, db: Session) -> int:
    service = _service(db)
    user = _require_user(service, args.email)
    service.update_user(user, UpdateUserCommand(role=Role(args.role)))
    print(f"✅ Conta {user.email} agora é {user.role}.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administração de contas do Scrinalia.")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Cria uma conta.")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=[role.value for role in Role], default=Role.CURATOR.value)
    create.add_argument("--password", help="Senha explícita; sem ela, uma temporária é gerada e impressa.")
    create.set_defaults(handler=_create)

    listing = commands.add_parser("list", help="Lista as contas da instalação.")
    listing.set_defaults(handler=_list)

    reset = commands.add_parser("reset-password", help="Define uma nova senha sem saber a antiga.")
    reset.add_argument("--email", required=True)
    reset.add_argument("--password", help="Senha explícita; sem ela, uma temporária é gerada e impressa.")
    reset.set_defaults(handler=_reset_password)

    activate = commands.add_parser("activate", help="Devolve o acesso a uma conta.")
    activate.add_argument("--email", required=True)
    activate.set_defaults(handler=_set_active, active=True)

    deactivate = commands.add_parser("deactivate", help="Tira o acesso de uma conta e encerra suas sessões.")
    deactivate.add_argument("--email", required=True)
    deactivate.set_defaults(handler=_set_active, active=False)

    role = commands.add_parser("set-role", help="Troca o papel de uma conta.")
    role.add_argument("--email", required=True)
    role.add_argument("--role", required=True, choices=[value.value for value in Role])
    role.set_defaults(handler=_set_role)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    with get_db() as db:
        unit_of_work = UnitOfWork(db)
        try:
            result = args.handler(args, db)
        except DomainException as exc:
            unit_of_work.rollback()
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        except IntegrityError as exc:
            unit_of_work.rollback()
            print(f"❌ Conflito no banco de dados: {exc.orig}", file=sys.stderr)
            return 1
        else:
            unit_of_work.commit()
            return result


if __name__ == "__main__":
    raise SystemExit(main())

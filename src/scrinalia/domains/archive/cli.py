"""
The collection catalogue from the host: the vocabulary out, and back in.

Run with ``uv run python -m scrinalia.domains.archive.cli``.

The vocabulary is **collection data**, and this module exists because of a decision about it: the
reference collection's arrangement tokens and terms are not versioned, so a fresh install comes up
with an empty catalogue. That is the honest state, and the one ADR 0008 already describes — an
installation that never declared its vocabulary refuses nothing of its own and inherits nobody
else's. What a fresh install *can* do is be brought to the state of the installation the file came
from, in one command, instead of typing rows.

``export`` writes the two catalogue tables to one JSON file; ``import`` reads a file back. The import
is idempotent and deliberately asymmetric, and the contract is worth stating exactly, because an
import that quietly did more would be a way to lose a curated catalogue:

- a term the file names that is **not** in the catalogue is created, carrying the file's ``is_active``
  so a retired row comes back retired instead of quietly resurrected;
- a term that is already there keeps its ``is_active`` — a name is corrected, a retirement is not
  undone — and the archivist's decision outlives an old file;
- nothing is ever deleted.

It runs on the host with the same repository the API uses, so the two cannot diverge: normalisation,
the unique keys and the meaning of a term's kind are the same code, not a second implementation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from scrinalia.core.database import get_db
from scrinalia.core.exceptions import DomainException
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.archive.repository.collection_vocabulary_repo import CollectionVocabularyRepository
from scrinalia.domains.archive.schemas.collection_vocabulary_schema import (
    CreateArrangementTermCommand,
    CreateCollectionTermCommand,
    UpdateArrangementTermCommand,
    UpdateCollectionTermCommand,
)

#: Where the file lives by default. ``Data/`` is the repository's gitignored drawer for data that
#: belongs to the installation, which is exactly what this is; the path is relative to the directory
#: the command runs from, so it is the repository root inside a checkout.
DEFAULT_PATH = Path("Data/vocabulary/collection_vocabulary.json")

#: Written into the file and ignored on the way back. It is for whoever opens the JSON by hand.
_DESCRIPTION = (
    "The collection's own vocabulary: the arrangement tokens its reference codes are built from, and "
    "the terms it carries as places or person names."
)


def _export(args: argparse.Namespace, db: Session) -> int:
    repo = CollectionVocabularyRepository(db)
    payload = {
        "description": _DESCRIPTION,
        "arrangement_terms": [
            {"token": term.token, "display_name": term.display_name, "is_active": term.is_active}
            for term in repo.list_arrangement_terms()
        ],
        # ``str`` and not the enum: the file is read by humans and by other tools, and a StrEnum
        # serialises as its value anyway — being explicit is what keeps the two the same string.
        "collection_terms": [
            {"term": term.term, "kind": str(term.kind), "is_active": term.is_active}
            for term in repo.list_collection_terms()
        ],
    }

    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"✅ {len(payload['arrangement_terms'])} tokens de arranjo e "
        f"{len(payload['collection_terms'])} termos de coleção escritos em {args.path}"
    )
    return 0


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DomainException(
            f"{path} não existe. O vocabulário é dado da instalação e não vem no repositório: "
            "gere o arquivo com `export` a partir de uma instalação que já o tenha, ou escreva-o à mão."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _import(args: argparse.Namespace, db: Session) -> int:
    payload = _read_payload(args.path)
    repo = CollectionVocabularyRepository(db)

    created = 0
    renamed = 0

    for item in payload.get("arrangement_terms", []):
        existing = repo.find_arrangement_term(item["token"])
        if existing is None:
            created_term = repo.create_arrangement_term(
                CreateArrangementTermCommand(token=item["token"], display_name=item["display_name"])
            )
            if item.get("is_active") is False:
                repo.update_arrangement_term(created_term, UpdateArrangementTermCommand(is_active=False))
            created += 1
        elif existing.display_name != item["display_name"]:
            repo.update_arrangement_term(existing, UpdateArrangementTermCommand(display_name=item["display_name"]))
            renamed += 1

    for item in payload.get("collection_terms", []):
        # The key is the pair: the same spelling can be a place in one catalogue and a person name in
        # another, and the table allows both. Looking it up by term alone would silently skip one.
        existing_term = repo.find_collection_term(item["term"], item["kind"])
        if existing_term is None:
            created_term = repo.create_collection_term(
                CreateCollectionTermCommand(term=item["term"], kind=item["kind"])
            )
            if item.get("is_active") is False:
                repo.update_collection_term(created_term, UpdateCollectionTermCommand(is_active=False))
            created += 1

    print(f"✅ {created} linha(s) criada(s), {renamed} nome(s) corrigido(s), nada apagado.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Catálogo do acervo: vocabulário de e para arquivo.")
    commands = parser.add_subparsers(dest="command", required=True)

    export = commands.add_parser("export", help="Escreve o vocabulário das tabelas em um arquivo JSON.")
    export.add_argument("--path", type=Path, default=DEFAULT_PATH, help=f"Destino (padrão: {DEFAULT_PATH}).")
    export.set_defaults(handler=_export)

    import_ = commands.add_parser(
        "import", help="Lê um arquivo JSON para as tabelas: cria o que falta, corrige nome, nunca apaga."
    )
    import_.add_argument("--path", type=Path, default=DEFAULT_PATH, help=f"Origem (padrão: {DEFAULT_PATH}).")
    import_.set_defaults(handler=_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    with get_db() as db:
        unit_of_work = UnitOfWork(db)
        try:
            result = args.handler(args, db)
        except (DomainException, json.JSONDecodeError, KeyError) as exc:
            # A malformed file is a typo in a file a person edited, not a defect: it gets a sentence
            # and a non-zero exit, not a traceback.
            unit_of_work.rollback()
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        else:
            unit_of_work.commit()
            return result


if __name__ == "__main__":
    raise SystemExit(main())

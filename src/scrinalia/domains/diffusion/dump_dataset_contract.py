"""Writes the dataset contract artifacts to ``packages/dataset-contract/<major>``.

Exists for the same reason ``api/dump_openapi.py`` does: the contract is an artifact the CI
regenerates and compares, not something only a running export produces. A schema the adapter writes
but nobody committed is a contract the consumer cannot read before downloading the data.

Usage::

    uv run python -m scrinalia.domains.diffusion.dump_dataset_contract
    uv run python -m scrinalia.domains.diffusion.dump_dataset_contract --output /tmp/dataset-contract

The default output is relative to the repository root, where ``bun run contract`` calls it from.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scrinalia.domains.diffusion.dataset_contract import contract_directory, contract_documents

DEFAULT_OUTPUT = Path("packages") / "dataset-contract" / contract_directory()


def main() -> None:
    """Dumps every artifact as deterministic JSON."""
    parser = argparse.ArgumentParser(description="Write the open dataset contract artifacts.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Directory to write into (default: {DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    for name, document in contract_documents().items():
        target = args.output / name
        target.write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()

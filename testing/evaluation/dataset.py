"""
Where the labelled evaluation sets live, and why they are not in this repository.

Both sets — ``retrieval_pairs.json`` and ``macro_category_pairs.json`` — are **collection data**:
real ``description_id``s, real titles, real tag names, and the curator's verdicts about them. They
are deliberately **not versioned**, so a clone carries the format and the code, never the acervo.
They live under ``Data/``, which the repository already keeps out of git for exactly this reason, or
wherever ``SCRINALIA_EVALUATION_DATA`` points.

The format of each file is documented in ``testing/evaluation/README.md``, which *is* versioned —
that is the point: the shape is part of the method, the rows are part of the collection.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

#: ``Data/`` is the repository's gitignored drawer for unpublished collection data. The environment
#: variable exists so a checkout can keep the sets somewhere else without editing the scripts.
DATA_DIR = Path(os.environ.get("SCRINALIA_EVALUATION_DATA", "Data/evaluation"))


def load_dataset(filename: str) -> dict[str, Any]:
    """
    Reads one labelled set, failing with what to do about it.

    A bare ``FileNotFoundError`` here would read like a broken checkout, and the first instinct would
    be to re-create the file from the code — which is the one thing that must not happen. The message
    says where the file belongs instead.
    """
    path = DATA_DIR / filename
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. The labelled set is collection data and is deliberately not "
            "versioned: keep it under Data/evaluation/ (or point SCRINALIA_EVALUATION_DATA at the "
            "directory that holds it). The expected shape is documented in "
            "testing/evaluation/README.md."
        )
    return json.loads(path.read_text(encoding="utf-8"))

"""The Python attribution and the SPA's ``attribution.ts`` are one fact in two languages.

ADR 0006 defines the four elements once for the interface; the dataset manifest needs the same
software identity in Python (ADR 0024). Two languages cannot share a module at runtime, so the pair is
pinned here: a change to one side that forgets the other fails before the release.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

from scrinalia.core.attribution import ATTRIBUTION

REPO_ROOT = Path(__file__).resolve().parents[3]
SPA_ATTRIBUTION = REPO_ROOT / "apps" / "curator" / "src" / "lib" / "attribution.ts"

#: TypeScript key -> dataclass field. The keys are the ones ``attribution.ts`` declares.
_KEYS = {
    "name": "name",
    "author": "author",
    "year": "year",
    "license": "license",
    "licenseUrl": "license_url",
    "sourceUrl": "source_url",
}


def _spa_values() -> dict[str, str]:
    """The six string literals of ``ATTRIBUTION``, read from the TypeScript source."""
    text = SPA_ATTRIBUTION.read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for ts_key, field in _KEYS.items():
        match = re.search(rf'\b{re.escape(ts_key)}:\s*"([^"]+)"', text)
        assert match, f"attribution.ts no longer declares '{ts_key}'"
        values[field] = match.group(1)
    return values


def test_the_python_attribution_matches_the_spa_definition() -> None:
    assert asdict(ATTRIBUTION) == _spa_values()

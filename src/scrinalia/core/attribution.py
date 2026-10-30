"""The author attribution, the Python half of the pair ``attribution.ts`` holds for the SPA.

ADR 0006 defines the four elements once, in ``apps/curator/src/lib/attribution.ts``. The open
dataset's manifest and the README inside the package (ADR 0024) need the same facts in Python, and the
two languages cannot share a module at runtime: a domain worker is installed without the SPA's source.
This is the pinned pair the constitution allows — ``testing/unit/core/test_attribution.py`` reads the
TypeScript file and fails when one side moves without the other.

The values are the software's identity, never the data license: a collection may be CC BY while the
software stays AGPL-3.0-only, and the two are separate fields in the manifest.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Attribution:
    """The four elements section 7(b) of the AGPL requires a modified version to keep displaying."""

    name: str
    author: str
    year: str
    license: str
    license_url: str
    source_url: str


#: The values mirrored from ``attribution.ts``; keep them in step through the pinning test.
ATTRIBUTION = Attribution(
    name="Scrinalia",
    author="CassioDalla",
    year="2026",
    license="AGPL-3.0-only",
    license_url="https://www.gnu.org/licenses/agpl-3.0.html",
    source_url="https://github.com/CassioDalla/Scrinalia",
)

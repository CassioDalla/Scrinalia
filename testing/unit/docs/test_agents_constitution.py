"""The constitution is a gate, not a promise: its size, its footer and its rule files are checked.

``AGENTS.md`` is the always-on instruction each session receives, and the DSH harness charges it
against a byte budget it truncates from the **tail** when it overflows. That is how a rule can be
written and never read: the file grew to 64,855 B against an effective cap of 65,244, so the section
added at the end was cut in the same edit that added it. The budget below is a ratchet: it only goes
down, and raising it is an amendment to the constitution's own Governance section.

The rule-file index is the other half. A rule that moved into a skill is only reachable if the
constitution names it, and a skill nobody cites is a rule nobody finds, so the two directions are
checked: every cited rule file exists, and every existing rule file is cited.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONSTITUTION = REPO_ROOT / "AGENTS.md"
SKILLS = REPO_ROOT / ".dsh" / "skills"

#: Ratchet, in bytes. Measured at 14,995 B when the constitution was ratified (2026-10-09), down from
#: 64,855 B; raise it only through the amendment procedure in its own Governance section.
BUDGET_BYTES = 16_000

#: A floor, so an emptied or truncated file fails loudly instead of trivially passing the ceiling.
MINIMUM_BYTES = 5_000

#: ``**Version**: 1.0.0 | **Ratified**: 2026-10-09 | **Last Amended**: 2026-10-09``
_FOOTER = re.compile(
    r"^\*\*Version\*\*: \d+\.\d+\.\d+ \| \*\*Ratified\*\*: \d{4}-\d{2}-\d{2} "
    r"\| \*\*Last Amended\*\*: \d{4}-\d{2}-\d{2}$",
    re.MULTILINE,
)

#: ``- `api` — the package's conventions ...`` in the ``## Rule files`` index.
_CITED = re.compile(r"^- `([a-z0-9-]+)` —", re.MULTILINE)

#: ``name: api`` in a skill's front matter.
_SKILL_NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


def constitution_text() -> str:
    """The constitution, as a single string."""
    return CONSTITUTION.read_text(encoding="utf-8")


def cited_rule_files() -> set[str]:
    """Rule files named by the ``## Rule files`` index."""
    index = constitution_text().split("## Rule files", 1)[1]
    return set(_CITED.findall(index))


def existing_rule_files() -> set[str]:
    """Skills on disk, each one a rule file."""
    return {path.parent.name for path in SKILLS.glob("*/SKILL.md")}


def test_constitution_stays_within_its_budget() -> None:
    """The file must fit the harness budget, and must not be empty."""
    size = len(CONSTITUTION.read_bytes())
    assert size >= MINIMUM_BYTES, f"AGENTS.md is {size} B: the constitution lost its content"
    assert size <= BUDGET_BYTES, (
        f"AGENTS.md is {size} B, over the {BUDGET_BYTES} B budget: at the harness cap the tail is "
        "truncated and the last rule is never read. Move the detail into a rule file, or amend the "
        "budget in AGENTS.md's Governance section."
    )


def test_constitution_declares_version_ratified_and_amended() -> None:
    """A governance document without a version and a date is not a constitution."""
    assert _FOOTER.search(constitution_text()), (
        "AGENTS.md must end with **Version**: x.y.z | **Ratified**: <date> | **Last Amended**: <date>"
    )


def test_constitution_cites_only_existing_rule_files() -> None:
    """A cited rule file that does not exist is a rule nobody can open."""
    missing = sorted(cited_rule_files() - existing_rule_files())
    assert not missing, f"AGENTS.md cites rule files that do not exist: {missing}"


def test_every_rule_file_is_cited_by_the_constitution() -> None:
    """A rule file the constitution does not cite is a rule nobody finds."""
    uncited = sorted(existing_rule_files() - cited_rule_files())
    assert not uncited, f"rule files exist that AGENTS.md does not cite: {uncited}"


def test_each_rule_file_declares_its_own_name() -> None:
    """The skill catalogue is keyed by ``name``, so it has to match the directory it lives in."""
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        declared = _SKILL_NAME.search(path.read_text(encoding="utf-8"))
        assert declared is not None, f"{path} has no name in its front matter"
        assert declared.group(1) == path.parent.name, (
            f"{path} declares name {declared.group(1)!r} but lives in {path.parent.name!r}: the skill "
            "catalogue would show a name that does not resolve to the file"
        )

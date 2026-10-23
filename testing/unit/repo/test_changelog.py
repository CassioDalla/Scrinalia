"""The changelog's release headings and its footer links are one set.

A changelog commit on 2026-10-17 replaced `## [1.2.0] - 2026-10-13` with a `### Fixed` heading while
adding an entry: the release notes of 1.2.0 were absorbed into the unreleased section, the footer
still carried `[1.2.0]`, and nothing failed because nothing read the file. This reads it.

The rules are the ones the file already followed: one section per release, one footer link per
section, the versions and their dates in descending order, and `[Unreleased]` comparing from the
newest release. `[Unreleased]` is a link without a section on purpose after a release — it points at
the compare view of what has landed since the tag.
"""

from __future__ import annotations

import re
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[3] / "CHANGELOG.md"

HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?$", re.MULTILINE)
LINK = re.compile(r"^\[(?P<version>[^\]]+)\]: (?P<url>\S+)$", re.MULTILINE)
RELEASE = re.compile(r"^\d+\.\d+\.\d+$")


def sections() -> list[tuple[str, str | None]]:
    return [(match["version"], match["date"]) for match in HEADING.finditer(CHANGELOG.read_text(encoding="utf-8"))]


def footer() -> dict[str, str]:
    return {match["version"]: match["url"] for match in LINK.finditer(CHANGELOG.read_text(encoding="utf-8"))}


def test_every_footer_link_has_a_section():
    versions = {version for version, _ in sections()}
    missing = sorted(set(footer()) - versions - {"Unreleased"})
    assert missing == [], f"footer link(s) without a section: {missing}"


def test_every_section_has_a_footer_link():
    missing = sorted({version for version, _ in sections()} - set(footer()))
    assert missing == [], f"section(s) without a footer link: {missing}"


def test_every_release_section_carries_its_date():
    undated = [version for version, date in sections() if version != "Unreleased" and date is None]
    assert undated == [], f"release section(s) without a date: {undated}"


def test_versions_descend():
    versions = [tuple(int(part) for part in version.split(".")) for version, _ in sections() if RELEASE.match(version)]
    assert versions == sorted(versions, reverse=True), versions


def test_dates_do_not_increase():
    dates = [date for _, date in sections() if date is not None]
    assert dates == sorted(dates, reverse=True), dates


def test_unreleased_compares_from_the_newest_release():
    newest = next(version for version, _ in sections() if RELEASE.match(version))
    assert footer()["Unreleased"].endswith(f"compare/v{newest}...HEAD"), footer()["Unreleased"]


def test_unreleased_is_the_first_section_when_present():
    versions = [version for version, _ in sections()]
    assert versions[0] == "Unreleased" or "Unreleased" not in versions, versions

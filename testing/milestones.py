"""The milestone invariants a release depends on.

The work that is left lives in the GitHub issues and their milestones (AGENTS.md, "Documentation and
language"), and a milestone **is** a release: `1.3 — Engine` closed on 2026-10-23, the day `1.3.0`
shipped. Four properties make that true, and none of them is "how many issues a milestone has" — the
count is a seed that grows while the work is measured (`1.3` was created with 4 issues and closed
with 22, and the 18 extra ones were found while doing the work).

1. A release milestone holds no `blocked` issue. A milestone closes when its issues close, so one
   that cannot close in the cycle — the public site, waiting for a curated set to publish — would
   make the milestone unclosable. `1.7` carried exactly that before 2026-10-23.
2. The reserved milestone holds no issue: `2.0` is spent by a MAJOR, not by backlog.
3. The 1.x numbers are contiguous, so a number is neither reused nor silently lost.
4. Every open issue has an open milestone, unless it is `blocked`: an issue outside a milestone has
   no release to land in, and an issue in a closed milestone cannot ship.

The rules are pure functions over the JSON the REST API returns, so `testing/unit/repo/` pins them
without a network, and `.github/workflows/milestones.yml` runs `main()` with the workflow's token.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from typing import Any

API = "https://api.github.com"
TITLE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+) — (?P<theme>\S.*)$")
RESERVED = "2.0 — Reserved"
BLOCKED = "blocked"


def label_names(issue: dict[str, Any]) -> set[str]:
    return {label["name"] for label in issue.get("labels", [])}


def title_parts(title: str) -> tuple[int, int] | None:
    match = TITLE.match(title)
    return (int(match["major"]), int(match["minor"])) if match else None


def _in(issue: dict[str, Any], number: int) -> bool:
    milestone = issue.get("milestone")
    return milestone is not None and milestone["number"] == number


def violations(milestones: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[str]:
    """Every way the open milestones and the open issues disagree with the four rules."""
    found: list[str] = []
    open_milestones = [milestone for milestone in milestones if milestone["state"] == "open"]
    open_numbers = {milestone["number"] for milestone in open_milestones}

    for milestone in open_milestones:
        parts = title_parts(milestone["title"])
        if parts is None:
            found.append(f"{milestone['title']!r} is not 'x.y — Theme'")
            continue
        major, _minor = parts
        if milestone["title"] == RESERVED:
            held = sum(1 for issue in issues if _in(issue, milestone["number"]))
            if held:
                found.append(f"{RESERVED!r} holds {held} open issue(s); it is spent by a MAJOR, not by backlog")
            continue
        if major >= 2:
            found.append(f"{milestone['title']!r} is a 2.x milestone; only the reserved one may exist")
        blocked = sorted(
            issue["number"] for issue in issues if _in(issue, milestone["number"]) and BLOCKED in label_names(issue)
        )
        if blocked:
            listed = ", ".join(f"#{number}" for number in blocked)
            found.append(f"{milestone['title']!r} holds blocked issue(s) {listed}; a milestone must be closable")

    minors: set[int] = set()
    for milestone in milestones:
        parts = title_parts(milestone["title"])
        if parts is not None and parts[0] == 1:
            minors.add(parts[1])
    if minors:
        missing = sorted(set(range(1, max(minors) + 1)) - minors)
        if missing:
            found.append(f"the 1.x sequence has a gap at {', '.join(f'1.{number}' for number in missing)}")

    for issue in issues:
        milestone = issue.get("milestone")
        if milestone is None:
            if BLOCKED not in label_names(issue):
                found.append(f"#{issue['number']} has no milestone and is not blocked")
            continue
        if milestone["number"] not in open_numbers:
            found.append(f"#{issue['number']} is in the closed milestone {milestone['title']!r}")

    return found


def _get(url: str, token: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload


def _all(path: str, token: str) -> list[dict[str, Any]]:
    separator = "&" if "?" in path else "?"
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _get(f"{API}{path}{separator}per_page=100&page={page}", token)
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def fetch(repo: str, token: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    milestones = _all(f"/repos/{repo}/milestones?state=all", token)
    issues = [issue for issue in _all(f"/repos/{repo}/issues?state=open", token) if "pull_request" not in issue]
    return milestones, issues


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not repo or not token:
        print("GITHUB_REPOSITORY and GH_TOKEN (or GITHUB_TOKEN) are required", file=sys.stderr)
        return 2
    milestones, issues = fetch(repo, token)
    found = violations(milestones, issues)
    for message in found:
        print(f"::error::{message}")
    if found:
        print(f"{len(found)} milestone violation(s)", file=sys.stderr)
        return 1
    print(f"{len(milestones)} milestone(s) and {len(issues)} open issue(s): no violation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

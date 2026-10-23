"""The milestone rules, pinned without a network.

`testing/milestones.py` is the one definition; this file feeds it the states that matter and asserts
the verdict, so the gate cannot pass by being wrong in the same way as the roadmap it checks. The
states are the ones the repository has actually been in: `1.7` holding the blocked public site, a
`2.0` that somebody filled, a `1.6` that disappeared between `1.5` and `1.7`.
"""

from __future__ import annotations

from typing import Any

from testing.milestones import violations


def milestone(number: int, title: str, state: str = "open") -> dict[str, Any]:
    return {"number": number, "title": title, "state": state}


def issue(number: int, attached: dict[str, Any] | None = None, labels: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"number": number, "milestone": attached, "labels": [{"name": name} for name in labels]}


def roadmap() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    engine = milestone(3, "1.3 — Engine", "closed")
    attribution = milestone(4, "1.4 — Attribution and verdict")
    contract = milestone(5, "1.5 — Readable contract")
    reserved = milestone(6, "2.0 — Reserved")
    milestones = [
        milestone(1, "1.1 — Curator and delivery", "closed"),
        milestone(2, "1.2 — Reference collection", "closed"),
        engine,
        attribution,
        contract,
        reserved,
    ]
    issues = [issue(135, attribution), issue(138, attribution), issue(93, contract)]
    return milestones, issues


def test_a_healthy_roadmap_has_no_violation():
    milestones, issues = roadmap()
    assert violations(milestones, issues) == []


def test_a_blocked_issue_inside_a_milestone_is_a_violation():
    milestones, issues = roadmap()
    issues.append(issue(46, milestones[3], ("blocked",)))
    found = violations(milestones, issues)
    assert any("#46" in message and "closable" in message for message in found), found


def test_a_blocked_issue_may_live_outside_a_milestone():
    milestones, issues = roadmap()
    issues.append(issue(46, None, ("blocked",)))
    assert violations(milestones, issues) == []


def test_an_open_issue_without_a_milestone_is_a_violation():
    milestones, issues = roadmap()
    issues.append(issue(151))
    found = violations(milestones, issues)
    assert any("#151" in message and "no milestone" in message for message in found), found


def test_the_reserved_milestone_must_stay_empty():
    milestones, issues = roadmap()
    issues.append(issue(999, milestones[5]))
    found = violations(milestones, issues)
    assert any("Reserved" in message and "MAJOR" in message for message in found), found


def test_a_gap_in_the_sequence_is_a_violation():
    milestones, issues = roadmap()
    milestones = [milestone for milestone in milestones if milestone["number"] != 3]
    found = violations(milestones, issues)
    assert any("gap" in message and "1.3" in message for message in found), found


def test_a_title_without_the_number_is_a_violation():
    milestones, issues = roadmap()
    milestones.append(milestone(7, "Scale and diffusion"))
    found = violations(milestones, issues)
    assert any("not 'x.y — Theme'" in message for message in found), found


def test_a_second_major_milestone_is_a_violation():
    milestones, issues = roadmap()
    milestones.append(milestone(7, "2.1 — Next"))
    found = violations(milestones, issues)
    assert any("2.x" in message for message in found), found


def test_an_open_issue_in_a_closed_milestone_is_a_violation():
    milestones, issues = roadmap()
    issues.append(issue(200, milestones[2]))
    found = violations(milestones, issues)
    assert any("#200" in message and "closed" in message for message in found), found

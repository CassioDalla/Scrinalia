"""MkDocs hook: report how far each documentation page is from the code it documents.

The decision is ADR 0010, and the reasoning is there. In one paragraph: coverage is a
**gate** (``testing/unit/docs/test_documentation_coverage.py`` walks the real catalogues and
fails on what a page forgot), freshness is a **report** (this file), and the judgement is
recorded in ``docs/log.md``.

Two rules make the report honest, and both are deliberate:

* **No page stores a revision.** A page cannot name the commit that contains it — the sha
  does not exist while the page is being written — so the marker is derived from git. An
  English page is a stale candidate when one of its ``sources:`` globs changed after the
  last commit that touched the page; a translation is a stale candidate when the page it
  translates changed after the last commit that touched the translation.
* **The report never fails the build.** Freshness is a judgement, and a build that fails on
  a judgement invites the blind "reviewed" bump that makes the tracking worthless. A broken
  link still fails, because ``mkdocs build --strict`` decides that, not this hook.

It runs on every build (so CI prints it for free) and alone:

    uv run python docs/_hooks/freshness.py [--repo .] [--all]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The generated, committed contract: the one place a route can be added, and therefore the
#: only file whose diff can be turned into "which operations changed" instead of "which
#: commits landed".
CONTRACT = "packages/api-contract/openapi.json"

#: The ledger of triage decisions, relative to the docs directory.
LEDGER = "log.md"

_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
_RANGE = re.compile(r"\*\*Range:\*\*\s*`?([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})`?")
_SOURCE_ITEM = re.compile(r"^\s+-\s+(.*)$")
_KEY_VALUE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")


class GitUnavailable(RuntimeError):
    """Raised when a git command fails; the caller reports it instead of failing the build."""


#: Set by :func:`on_config`; the i18n plugin calls the hook once per language.
_reported = False


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout, raising :class:`GitUnavailable` on failure."""
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if done.returncode != 0:
        raise GitUnavailable(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout


def parse_front_matter(text: str) -> dict[str, Any]:
    """Read the fixed subset of YAML front matter a page is allowed to declare.

    The hook deliberately does not depend on a YAML parser. The two keys have one shape
    each — a list of globs (``sources:``) and a path (``translation_of:``) — the shape is
    pinned by tests, and a dependency-free reader is what lets those tests import *this*
    implementation instead of keeping a second copy of the rule, which is how a shipped
    check and its test start disagreeing.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, Any] = {}
    key: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        item = _SOURCE_ITEM.match(line)
        if item is not None and key is not None:
            value = meta.get(key)
            if not isinstance(value, list):
                value = []
                meta[key] = value
            value.append(item.group(1).strip())
            continue
        pair = _KEY_VALUE.match(line)
        if pair is not None:
            name = pair.group(1)
            key = name
            meta[name] = pair.group(2).strip()
    return meta


def _pathspec(source: str) -> str:
    """Turn a declared source into a pathspec git accepts (``dir/**`` -> ``dir/``)."""
    return f"{source[:-3]}/" if source.endswith("/**") else source


def _specs(sources: list[str]) -> list[str]:
    return [_pathspec(source) for source in sources]


def _last_commit(repo: Path, path: Path) -> str:
    return git(repo, "log", "-1", "--format=%h", "--", path.relative_to(repo).as_posix()).strip()


def _later(repo: Path, first: str, second: str) -> str:
    """Return whichever of two revisions is a descendant of the other."""
    if not first:
        return second
    if not second:
        return first
    return second if git(repo, "rev-list", "--count", f"{first}..{second}").strip() != "0" else first


def _commits(repo: Path, revision: str, sources: list[str]) -> list[str]:
    out = git(repo, "log", "--format=%h %s", f"{revision}..HEAD", "--", *_specs(sources))
    return [line for line in out.splitlines() if line.strip()]


def _files(repo: Path, revision: str, sources: list[str]) -> list[str]:
    out = git(repo, "diff", "--name-only", f"{revision}..HEAD", "--", *_specs(sources))
    return [line for line in out.splitlines() if line.strip()]


def _routes(document: dict[str, Any]) -> set[str]:
    routes: set[str] = set()
    for path, operations in (document.get("paths") or {}).items():
        for method in operations:
            if method.lower() in _METHODS:
                routes.add(f"{method.upper()} {path}")
    return routes


def route_delta(repo: Path, revision: str) -> tuple[list[str], list[str]]:
    """Operations added and removed since ``revision``, read from the committed contract."""
    try:
        before = _routes(json.loads(git(repo, "show", f"{revision}:{CONTRACT}")))
    except (GitUnavailable, json.JSONDecodeError):
        return [], []
    after = _routes(json.loads((repo / CONTRACT).read_text(encoding="utf-8")))
    return sorted(after - before), sorted(before - after)


def ledger_floor(docs_dir: Path) -> str:
    """The end of the last triaged range in ``docs/log.md``, or an empty string."""
    ledger = docs_dir / LEDGER
    if not ledger.exists():
        return ""
    matches = _RANGE.findall(ledger.read_text(encoding="utf-8"))
    return matches[-1][1] if matches else ""


@dataclass(frozen=True)
class Page:
    """One documentation page and the front matter it declares."""

    rel: str
    path: Path
    meta: dict[str, Any]


def pages(docs_dir: Path) -> list[Page]:
    """Every page that can be a stale candidate: not an ADR, not the ledger itself."""
    found: list[Page] = []
    for path in sorted(docs_dir.rglob("*.md")):
        rel = path.relative_to(docs_dir).as_posix()
        if rel.startswith("adr/") or rel == LEDGER or rel.startswith("_"):
            continue
        found.append(Page(rel, path, parse_front_matter(path.read_text(encoding="utf-8"))))
    return found


def _stale_sources(repo: Path, docs_dir: Path, page: Page, floor: str) -> str | None:
    """The report block of a stale English page, or ``None`` when the page is current."""
    sources = page.meta.get("sources")
    if not isinstance(sources, list) or not sources:
        return None
    revision = _later(repo, _last_commit(repo, page.path), floor)
    commits = _commits(repo, revision, sources)
    if not commits:
        return None
    block = [f"{page.rel}", f"    its sources moved since the page was last touched ({revision}):"]
    block += [f"      - {name}" for name in _files(repo, revision, sources)]
    block += ["    commits:"] + [f"      {commit}" for commit in commits]
    if CONTRACT in _files(repo, revision, sources):
        added, removed = route_delta(repo, revision)
        if added or removed:
            block.append("    API delta:")
            block += [f"      + {route}" for route in added]
            block += [f"      - {route}" for route in removed]
    return "\n".join(block)


def _stale_translation(repo: Path, docs_dir: Path, page: Page, floor: str) -> str | None:
    """The report block of a stale translation, or ``None`` when it is current."""
    target = page.meta.get("translation_of")
    if not isinstance(target, str) or not target:
        return f"{page.rel}\n    no `translation_of:` declared — the translation has no source"
    translated = (docs_dir / target).resolve()
    if not translated.exists():
        return f"{page.rel}\n    `translation_of: {target}` does not exist"
    target_rel = translated.relative_to(repo).as_posix()
    revision = _later(repo, _last_commit(repo, page.path), floor)
    commits = _commits(repo, revision, [target_rel])
    if not commits:
        return None
    block = [f"{page.rel}", f"    the page it translates changed after the translation ({revision}):"]
    block += [f"      {commit}" for commit in commits]
    return "\n".join(block)


def build_report(repo: Path, docs_dir: Path, *, everything: bool = False) -> str:
    """Build the whole report; ``everything`` ignores the ledger floor."""
    floor = "" if everything else ledger_floor(docs_dir)
    blocks: list[str] = []
    for page in pages(docs_dir):
        if "translation_of" in page.meta:
            block = _stale_translation(repo, docs_dir, page, floor)
        elif "sources" in page.meta:
            block = _stale_sources(repo, docs_dir, page, floor)
        else:
            # Not a tracked page (the site index). Which pages must declare `sources:` is an
            # exact partition owned by testing/unit/docs/test_docs_frontmatter.py, so this
            # report never guesses.
            continue
        if block is not None:
            blocks.append(block)
    header = ["Documentation freshness (ADR 0010)"]
    header.append(
        "Every page is fresh: no declared source moved after the last commit that touched it."
        if not blocks
        else f"{len(blocks)} page(s) to look at:"
    )
    if floor and not everything:
        header.append(f"Closed by docs/{LEDGER} up to {floor}; pass --all to ignore it.")
    return "\n".join([*header, ""] + [f"{block}\n" for block in blocks]).rstrip() + "\n"


def _docs_dir(repo: Path) -> Path:
    return repo / "docs"


def on_config(config: Any, **_kwargs: Any) -> Any:
    """MkDocs hook entry point. A report must never break a build, so it never raises.

    The i18n plugin builds each language through a configuration cycle, so this hook runs once per
    language; the report is about the repository, not about a language, and the flag prints it once.
    """
    global _reported  # one flag for one process-wide report
    try:
        if not _reported:
            _reported = True
            docs_dir = Path(config["docs_dir"]).resolve()
            print(build_report(docs_dir.parent, docs_dir))
    except Exception as error:  # the freshness report is not a gate
        print(f"[freshness] report unavailable: {error}")
    return config


def main(argv: list[str] | None = None) -> int:
    """Print the report without building the site."""
    parser = argparse.ArgumentParser(description="Report how far each page is from its sources.")
    parser.add_argument("--repo", default=".", help="repository root (default: the working directory)")
    parser.add_argument("--all", action="store_true", help="ignore the ledger floor in docs/log.md")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    print(build_report(repo, _docs_dir(repo), everything=args.all))
    return 0


if __name__ == "__main__":
    sys.exit(main())

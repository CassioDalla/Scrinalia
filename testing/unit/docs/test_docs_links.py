"""Every in-site link resolves to a page, and every anchor to a heading on it.

``mkdocs build --strict`` fails on a link to a missing **file**, and says nothing about a link to a
missing **anchor**: ``page.md#gone`` renders a link that answers 404 and the build stays green. The
list of headings is what makes an anchor checkable without a browser, and the i18n structure adds
one rule — a Portuguese page links the canonical name (``install.md``) and the reader lands on
``install.pt.md``, so the anchor has to be looked up in the translation when there is one.

This is the check that caught a real defect while the guides were being written: the Portuguese page
linked ``#envexample-and-coreconfigpy`` while its translated heading slugifies to
``envexample-e-coreconfigpy``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs"

#: ``[text](target)``, the inline form the pages use. Reference-style links are not used.
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^\s*```")


def slug(text: str) -> str:
    """The anchor ``python-markdown`` generates for a heading, accents folded.

    Kept in step with the toc extension: ASCII-fold, lowercase, drop everything that is not a word
    character, a space or a hyphen, then spaces to hyphens.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    folded = re.sub(r"[^\w\s-]", "", folded.lower())
    return re.sub(r"-+", "-", re.sub(r"\s+", "-", folded)).strip("-")


def headings(path: Path) -> set[str]:
    """Every anchor a page offers, ignoring the ``#`` lines inside fenced code blocks."""
    found: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match is not None:
            found.add(slug(match.group(2)))
    return found


def pages() -> list[Path]:
    return sorted(path for path in DOCS.rglob("*.md") if "_hooks" not in path.parts)


def landing_page(page: Path, target: Path) -> Path:
    """The page a reader of ``page`` lands on when the link names ``target``.

    The anchor is checked against the page the **browser** will open, which is not always the file
    the link names. The i18n build rewrites an in-site link to the reader's language and keeps the
    anchor exactly as written (measured on the built site: a Portuguese page linking
    ``guides/operate.md#limites-conhecidos-e-trade-offs-aceitos`` renders
    ``guides/operate/#limites-conhecidos-e-trade-offs-aceitos``, and the Portuguese heading is what
    carries that id). So a translated page that links a canonical file has to offer the **translated**
    anchor, and an English page keeps the canonical one. A link that names the translated file, or a
    page with no translation, is looked at as it is.
    """
    if not page.name.endswith(".pt.md"):
        return target
    if target.name.endswith(".pt.md"):
        return target
    twin = target.with_name(target.name.removesuffix(".md") + ".pt.md")
    return twin if twin.exists() else target


def test_every_declared_page_is_reachable_from_the_nav_or_another_page() -> None:
    """A page nobody links to is a page nobody reads.

    ``mkdocs build --strict`` does not fail on a page missing from the navigation (it logs it at
    INFO), so this is where an orphan is caught. A translation is reached through the canonical
    name — every page links ``install.md`` and the reader gets ``install.pt.md`` — so the
    translated file counts as reached when its twin is.
    """
    linked: set[str] = set()
    for page in pages():
        body = page.read_text(encoding="utf-8")
        for target in _LINK.findall(body):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path = target.split("#", 1)[0]
            if not path:
                continue
            resolved = (page.parent / path).resolve()
            if resolved.exists():
                linked.add(resolved.relative_to(DOCS).as_posix())

    def reached(rel: str) -> bool:
        if rel in linked:
            return True
        return rel.endswith(".pt.md") and f"{rel.removesuffix('.pt.md')}.md" in linked

    # ``index.md`` is the front door and ``adr/index.md`` is the index of the decisions; both are
    # reached from the navigation, which is the one place a link is not a Markdown link.
    unreachable = [
        page.relative_to(DOCS).as_posix()
        for page in pages()
        if not reached(page.relative_to(DOCS).as_posix()) and page.name not in {"index.md", "index.pt.md"}
    ]
    assert not unreachable, f"no page links to: {unreachable}"


def test_every_in_site_link_resolves_to_a_page_and_an_anchor() -> None:
    broken: list[str] = []
    for page in pages():
        body = page.read_text(encoding="utf-8")
        for target in _LINK.findall(body):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, anchor = target.partition("#")
            target_page = page if not path else page.parent / path
            if not target_page.exists():
                broken.append(f"{page.name}: `{target}` points at a file that does not exist")
                continue
            if not anchor:
                continue
            # The anchor belongs to the page the browser opens, not necessarily to the file the
            # link names: a translated page that links a canonical file lands on the translation.
            landing = landing_page(page, target_page)
            if anchor not in headings(landing):
                broken.append(
                    f"{page.name}: `{target}` — no heading in `{landing.relative_to(DOCS)}` slugifies to `{anchor}`"
                )
    assert not broken, "broken in-site links:\n  " + "\n  ".join(broken)

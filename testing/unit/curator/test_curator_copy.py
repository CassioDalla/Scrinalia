"""The curator SPA's copy contract (issue #23).

Four rules that no green gate could see before, each one the day after a defect that shipped:

1. **A design token exists, and is written the way Tailwind v4 needs it.** `bg-[--color-surface]`
   compiles to `background-color: --color-surface` — invalid CSS the browser drops *silently*, which
   is how 105 of them shipped with `tsc`, ESLint and the Vite build all green. The parenthesised form
   fixed that, and then `bg-(--color-surface-2)` named a token `styles.css` never defined and did the
   same thing again: valid syntax, undefined variable, no background. So the test checks both halves.
2. **The product's name is defined once.** `lib/attribution.ts` owns it because the license
   obligation points at that file; `index.html` used to type it a second time, where no component
   could see it and a rename would not reach it.
3. **A screen's heading comes from the catalogue.** `lib/screens.ts` holds the label the menu, the
   settings card and the `<h1>` all read; a route names its screen and cannot pass a heading of its
   own. That is what makes "the menu says `Tags` and the page says *Vocabulário de tags*" impossible
   instead of merely repaired.
4. **A retired word does not come back.** The one-verb-per-action canon of `lib/copy.ts` is prose
   too, and prose is where it leaked: `components/hierarchy/MaterialisationPanel.tsx` kept saying
   `rung`, `apply` and `dry-run` through the whole review, because it is a **component and not a
   screen** — the per-screen pass never opened it, and nothing failed. This is the rule that makes
   the next one fail.

The parser is deliberately textual. The SPA has no test runner of its own (there is no `vitest` and
this is not the change that adds one), and the four rules are about *source text* — a token spelled
wrong, a name typed twice, a heading written by hand, a word that should be gone — which is exactly
what a text scan can decide.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CURATOR = REPO_ROOT / "apps" / "curator"
SRC = CURATOR / "src"

STYLES = SRC / "styles.css"
ATTRIBUTION = SRC / "lib" / "attribution.ts"
SCREENS = SRC / "lib" / "screens.ts"
ROUTER = SRC / "router.tsx"
INDEX_HTML = CURATOR / "index.html"
MAIN_TSX = SRC / "main.tsx"

#: The form Tailwind v4 needs, and the form that compiles to nothing.
TOKEN = re.compile(r"\(--color-([a-z0-9-]+)\)")
BRACKET_TOKEN = re.compile(r"\[--[a-z]")
VAR_TOKEN = re.compile(r"var\(--color-([a-z0-9-]+)\)")

#: Every source file of the SPA. `dist/` is excluded: it is generated, and it is where a stale build
#: would hide the defect the gate exists to catch.
SOURCES = sorted(
    path for pattern in ("*.ts", "*.tsx", "*.css") for path in SRC.rglob(pattern) if path.name != "schema.d.ts"
)

#: The words this interface retired, and what it says instead. Each one was in the tree when the
#: canon landed, and each one is now at zero — the gate is what keeps it there.
#:
#: What is deliberately **not** here, because it cannot be decided from the text alone:
#:
#: * `gravar` in the sense of *recording* — "o veredito é gravado", "o validador gravou este código",
#:   "cada aplicação grava uma entrada" — which is not the `Salvar` action and reads correctly. Only
#:   the action was retired ("não pode `gravar` um nível" became "não pode salvar").
#: * `desativar`, which is the right verb for an **account** and the retired one for a **catalogue
#:   row** (`Aposentar`). Which object it acts on is not in the word.
RETIRED = {
    r"\brungs?\b": "the Portuguese UI says `degrau` (`rung` is the English of the code and the docs)",
    r"\bunific\w*": "the merge is `Mesclar`",
    r"\bapag\w*": "destroying stored data is `Excluir`",
    r"\bcadastr\w*": "creating a row is `Criar`",
    r"\bexecuta(?:r|ndo|do|da|dos|das|ou)?\b": "launching a run is `Rodar agora` (`execução` is the noun)",
    r"\bapply\b": "the batch commit is `aplicação`",
    r"\bdry-run\b": "the preview is `prévia`",
    r"\bundo\b": "walking a ledger back is `Desfazer`",
    # The two words the interface kept as metaphors after the contract had already named the concept:
    # the API's field is `category` and its reason enum is `TRIGRAM, PLURAL, MIXED` for a *cluster*.
    # `gaveta` ("drawer") and `cluster` were the interface's own vocabulary for both, which is the
    # split this whole test exists to close.
    r"\bgavetas?\b": "the subject axis is `Categoria` — the contract calls it `category`",
    r"\bclusters?\b": "the grouping is `agrupamento`",
}

#: A legitimate use of a retired word, with the reason it is legitimate. Empty is the normal state:
#: the map exists so that an exception is a line in a diff a reviewer reads, and not a hole in the
#: pattern. ``(file, the text as it appears, why)``.
ALLOWED: tuple[tuple[str, str, str], ...] = ()

#: A double-quoted literal, and a JSX text node. Both are what a person can read on the screen.
LITERAL = re.compile(r'"([^"\n]{2,})"')
#: The text node allows **newlines**, and that is not a detail: a sentence the formatter wrapped
#: across two lines is one string, and a pattern that stopped at the newline read only its first
#: half. `só o apply absorve as tags` sat on the second line and went unseen by the whole review
#: pass *and* by the first version of this gate — the rendered screen is what showed it.
JSX_TEXT = re.compile(r'>([^<>{}"]{2,})<')
#: A template literal. It was the third hole and the rendered screen found it too: the categories
#: subtitle is built as `` `${n} descrições com gaveta` ``, a backtick string, and the extractor read
#: only double quotes. `${…}` is dropped before the words are read, because the expression is code.
TEMPLATE = re.compile(r"`([^`]{2,})`")
COMMENT = re.compile(r"/\*.*?\*/|^\s*//[^\n]*", re.M | re.S)

#: A path — a contract route or a front-end one — which is an identifier and never copy. It is why
#: `'/api/v1/hierarchy/materialisation/apply'` in `api/client.ts` is not a use of the retired word:
#: it is the name of an operation, and no screen renders it. (The one place a path *is* shown —
#: `NerExclusionsRoute`'s link text — is a JSX text node, and the node pattern requires a letter
#: first, so it is not read as a path and not read as copy either.)
PATH = re.compile(r"^/[^\s]*$")


def visible_strings(path: Path) -> list[str]:
    """Every string of a source file that can reach the screen.

    Comments are read out first: they are English, they carry `rung` and `apply` on purpose, and a
    comment is not copy. The extraction is a scan and not a parser — every double-quoted literal and
    every JSX text node, the latter with its whitespace collapsed — which is why a legitimate use of
    a retired word needs an entry in `ALLOWED` instead of a cleverer pattern.
    """
    body = COMMENT.sub("", text(path))
    nodes = [" ".join(node.split()) for node in JSX_TEXT.findall(body)]
    templates = [re.sub(r"\$\{[^}]*\}", " ", t) for t in TEMPLATE.findall(body)]
    found = LITERAL.findall(body) + [node for node in nodes if re.search(r"[A-Za-zÀ-ÿ]", node)]
    found += [" ".join(t.split()) for t in templates if re.search(r"[A-Za-zÀ-ÿ]", t)]
    return [value for value in found if not PATH.match(value)]


def test_no_retired_word_is_visible() -> None:
    """The canon of `lib/copy.ts`, held over every string the archivist can read."""
    offenders: list[str] = []
    for path in SOURCES:
        relative = path.relative_to(CURATOR).as_posix()
        for value in visible_strings(path):
            if any(relative == file and allowed in value for file, allowed, _ in ALLOWED):
                continue
            for pattern, instead in RETIRED.items():
                if re.search(pattern, value, re.I):
                    offenders.append(f"{relative}: {value.strip()[:70]!r} — {instead}")
    assert not offenders, (
        "these user-visible strings use a word the interface retired:\n  "
        + "\n  ".join(sorted(set(offenders)))
        + "\n\nThe canon lives in `apps/curator/src/lib/copy.ts`; if a use is legitimate, add it to "
        "`ALLOWED` in this test with the reason, so the exception is a line a reviewer reads."
    )


def test_the_extractor_sees_strings(tmp_path: Path) -> None:
    """A sanity check on the scan itself, so a broken pattern fails instead of passing silently.

    The input is **synthetic**: the behaviour under test is the scan, not the copy of the day. The
    first version of this test pinned the hint "As gavetas de assunto" and broke the day the copy
    was rewritten — a test failing for doing its job. Copy changes; the scan must not care.
    """
    sample = tmp_path / "Sample.tsx"
    sample.write_text('export const SAMPLE = { label: "Um rótulo qualquer" };\n', encoding="utf-8")
    assert any(value == "Um rótulo qualquer" for value in visible_strings(sample)), (
        "the extractor no longer reads a double-quoted literal."
    )

    # A backtick string is copy when it has words: the categories subtitle is one, and the first
    # extractor read only double quotes, so a retired word inside it was invisible to the gate.
    sample.write_text("const s = `${n} descrições com gaveta`;\n", encoding="utf-8")
    assert any("descrições com gaveta" in value for value in visible_strings(sample)), (
        "the extractor no longer reads a template literal; every word inside one is ungated."
    )

    seen = visible_strings(SCREENS)
    assert len(seen) > 20, f"the extractor found {len(seen)} strings in `lib/screens.ts`; the pattern is broken."


def test_the_extractor_joins_a_wrapped_text_node(tmp_path: Path) -> None:
    """A sentence the formatter wrapped across two lines is **one** string.

    The first version of the pattern stopped at the newline and read only the first half, which is
    how `só o apply absorve as tags` survived the whole review pass *and* the gate — the rendered
    screen is what showed it. Synthetic input, for the same reason as above.
    """
    sample = tmp_path / "Sample.tsx"
    sample.write_text(
        "export function Sample() {\n"
        "  return (\n"
        "    <p>\n"
        "      primeira linha da frase\n"
        "      segunda linha com apply dentro\n"
        "    </p>\n"
        "  );\n"
        "}\n",
        encoding="utf-8",
    )
    assert any("segunda linha com apply dentro" in value for value in visible_strings(sample)), (
        "the extractor no longer joins a JSX text node across lines; the retired-word rule has a "
        "hole for every sentence the formatter wrapped."
    )


def text(path: Path) -> str:
    """The whole source of a file, or an empty string when it does not exist."""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def defined_tokens() -> set[str]:
    """The colour tokens `@theme` actually defines."""
    theme = text(STYLES).split("@theme", 1)
    assert len(theme) == 2, "`styles.css` has no `@theme` block: the palette has to live somewhere."
    return set(re.findall(r"--color-([a-z0-9-]+):", theme[1]))


def test_every_colour_token_used_exists() -> None:
    """A token that is not in the theme renders nothing, and nothing is exactly what you see."""
    defined = defined_tokens()
    assert defined, "no colour token is defined in `styles.css`."
    unknown: dict[str, list[str]] = {}
    for path in SOURCES:
        for name in set(TOKEN.findall(text(path))) | set(VAR_TOKEN.findall(text(path))):
            if name not in defined:
                unknown.setdefault(name, []).append(path.relative_to(CURATOR).as_posix())
    assert not unknown, (
        f"these colour tokens are used but not defined in `src/styles.css`: "
        f"{ {name: sorted(files) for name, files in unknown.items()} }. Tailwind compiles the "
        "reference and the browser drops the declaration, so the element renders with no colour."
    )


def test_no_token_uses_the_bracket_form() -> None:
    """The form that compiles to invalid CSS, and that a green build cannot see."""
    offenders = [
        f"{path.relative_to(CURATOR).as_posix()}:{number}"
        for path in SOURCES
        for number, line in enumerate(text(path).splitlines(), start=1)
        if BRACKET_TOKEN.search(line)
    ]
    assert not offenders, (
        f"these lines use the bracket form of a design token: {offenders}. Tailwind v4 needs "
        "parentheses — `bg-(--color-surface)`, not `bg-[--color-surface]` — because the bracket form "
        "compiles to `background-color: --color-surface`, which the browser drops silently."
    )


def test_the_product_name_is_written_once() -> None:
    """One definition, in the file the license obligation already points at."""
    match = re.search(r'name:\s*"([^"]+)"', text(ATTRIBUTION))
    assert match, "`lib/attribution.ts` no longer declares the display name."
    name = match.group(1)

    offenders = [
        path.relative_to(CURATOR).as_posix()
        for path in sorted(CURATOR.rglob("*"))
        if path.is_file()
        and path.suffix in {".ts", ".tsx", ".html", ".json", ".css"}
        and path != ATTRIBUTION
        and "dist" not in path.parts
        and "node_modules" not in path.parts
        and name in text(path)
    ]
    assert not offenders, (
        f"the product's name is typed outside `lib/attribution.ts`, which owns it: {offenders}. "
        "A second copy is a second thing to forget — the license notice points at the first one."
    )

    assert "document.title" in text(MAIN_TSX), (
        "`main.tsx` no longer writes the tab's title from the one definition of the name; the name "
        "would have to be typed into `index.html` again."
    )


def _screen_records() -> dict[str, tuple[str, bool]]:
    """Every entry of `SCREENS`, keyed by its id: its path, and whether its heading is dynamic."""
    body = text(SCREENS).split("export const SCREENS", 1)
    assert len(body) == 2, "`lib/screens.ts` no longer exports `SCREENS`."
    records: dict[str, tuple[str, bool]] = {}
    for block in re.finditer(r"\n  (\w+): \{(.*?)\n  \},", body[1], re.S):
        identifier, entry = block.group(1), block.group(2)
        path = re.search(r'path:\s*"([^"]+)"', entry)
        assert path, f"`SCREENS.{identifier}` has no path, so no route can be matched to it."
        records[identifier] = (path.group(1), "dynamicTitle: true" in entry)
    assert records, "`lib/screens.ts` declares no screen."
    return records


def _routes() -> dict[str, str]:
    """Every route of `router.tsx`, keyed by its path: the component that renders it."""
    records: dict[str, str] = {}
    for block in re.finditer(r"createRoute\(\{(.*?)\n\}\);", text(ROUTER), re.S):
        entry = block.group(1)
        path = re.search(r'path:\s*"([^"]+)"', entry)
        component = re.search(r"component:\s*(\w+)", entry)
        assert path and component, f"a route in `router.tsx` has no path or no component:\n{entry[:200]}"
        records[path.group(1)] = component.group(1)
    assert records, "`router.tsx` declares no route."
    return records


def test_every_route_has_a_named_screen() -> None:
    """A route without a name is a screen the menu, the card and the heading cannot agree on."""
    screens = _screen_records()
    routes = _routes()
    named = {path for path, _ in screens.values()}
    missing = sorted(set(routes) - named)
    assert not missing, (
        f"these routes of `apps/curator/src/router.tsx` have no entry in `lib/screens.ts`: {missing}. "
        "Every screen has one name, and it is the one the menu, the settings card and the `<h1>` read."
    )
    orphaned = sorted(named - set(routes))
    assert not orphaned, (
        f"`lib/screens.ts` names screens that `router.tsx` does not declare: {orphaned}. "
        "A name for a route that does not exist is a menu entry that leads nowhere."
    )


def test_every_heading_comes_from_the_screens_catalogue() -> None:
    """The heading is not a prop a route can get wrong; it names its screen and the catalogue answers."""
    screens = _screen_records()
    by_path = {path: identifier for identifier, (path, _) in screens.items()}
    dynamic = {identifier for identifier, (_, is_dynamic) in screens.items() if is_dynamic}

    by_component: dict[str, Path] = {}
    for path in sorted((SRC / "routes").glob("*.tsx")):
        for component in re.findall(r"export function (\w+Route)\b", text(path)):
            by_component[component] = path

    failures: list[str] = []
    for path, component in _routes().items():
        identifier = by_path[path]
        if identifier in dynamic:
            continue
        source = by_component.get(component)
        assert source, f"no file in `src/routes/` exports `{component}` for `{path}`."
        body = text(source)
        if f'screen="{identifier}"' not in body:
            failures.append(f'{source.name} does not pass `screen="{identifier}"`')
        elif re.search(r"<PageHeader[^>]*\stitle=", body):
            failures.append(f"{source.name} passes a `title` to `<PageHeader>` as well")

    assert not failures, (
        f"the page heading is not taken from `lib/screens.ts`: {failures}. The `<h1>` is the menu's "
        "label, resolved by `PageHeader` from the screen id — a heading typed in the route is a "
        "second definition, and it is the one that drifted."
    )

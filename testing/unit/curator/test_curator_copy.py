"""The curator SPA's copy contract (issue #23).

Five rules that no green gate could see before, each one the day after a defect that shipped:

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
5. **Two screens that share a vocabulary name each other, by the route and not by the tab.** #232
   found `Não é Assunto` and `Termos Bloqueados` reading as one screen with two filters, and the one
   link between them dropped the reader on the Tags screen's default tab. The link is now a source
   fact: each route contains `to="<the other's path>"`, and the paths are read from `SCREENS`, so a
   rename fails here instead of orphaning the referent again.

The parser is deliberately textual. The SPA has no test runner of its own (there is no `vitest` and
this is not the change that adds one), and the five rules are about *source text* — a token spelled
wrong, a name typed twice, a heading written by hand, a word that should be gone, a link that points
nowhere — which is exactly what a text scan can decide.
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

#: The Portuguese catalogue: where the copy lives now (ADR 0020 §1), and what the extractor's own
#: sanity check reads instead of `lib/screens.ts`.
CATALOGUE = SRC / "i18n" / "pt.ts"

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
    r"\bexecuta(?:r|ndo|do|da|dos|das|ou)?\b": "launching a run is `Enfileirar execução` (`execução` is the noun)",
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
        # The canon is about the Portuguese interface: the English catalogue is allowed to say
        # "Apply" and "Undo", which are the correct English for `Aplicar` and `Desfazer`.
        if relative == "src/i18n/en.ts":
            continue
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


def test_the_blocked_spellings_are_named_one_way() -> None:
    """#232: one place, three names — the tab's, the SPA's hint, and the guides' section.

    The rename in `7e9a5b3` left `lib/taxonomy.ts` telling the reader "na aba Stopwords" and two
    route strings promising the old tab, one rename later. The **name** is what this pins: the
    proper noun the tab carried, not the code's word. `domain_stopwords`, `stopwords(axis)` and the
    `STOPWORD` status code are identifiers and enum members, and retiring them from the source would
    be a test that fails on the contract.

    Case matters here: the label was `Termos Bloqueados`, the code is `stopwords`, and the two are
    told apart by the capital letter that only copy has.
    """
    retired_names = re.compile(r"\bStopwords?\b|\bTermos Bloqueados\b")
    offenders = [
        f"{path.relative_to(CURATOR).as_posix()}: {value.strip()[:70]!r}"
        for path in SOURCES
        for value in visible_strings(path)
        if retired_names.search(value)
    ]
    assert not offenders, (
        "these user-visible strings still name the screen `Stopwords` or `Termos Bloqueados`: "
        f"{offenders}. The name is `Grafias bloqueadas`, and a reference to the *place* is what "
        "went stale twice; the label itself lives in `i18n/pt.ts` (`screens.blockedSpellings`)."
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

    seen = visible_strings(CATALOGUE)
    assert len(seen) > 20, f"the extractor found {len(seen)} strings in `src/i18n/pt.ts`; the pattern is broken."


#: What a person reads as Portuguese. The catalogue is excluded: it *is* the Portuguese copy.
PORTUGUESE = re.compile(
    r"[áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ]|"
    r"\b(não|uma|com|para|que|das|dos|pela|pelo|sem|como|quando|também|já|ainda|só|ser|está|são|"
    r"você|seu|sua|seus|suas|nesta|neste|deste|desta|após|até|entre|sobre|pode|podem|deve|devem|"
    r"fazer|feito|vai|vão|tem|têm|nunca|sempre|nada|tudo|outro|outra|mais|menos|muito|pouco|aqui|"
    r"onde|quem)\b",
    re.I,
)

#: The files that still hold Portuguese, and the ratchet. A file leaves this list when its screen is
#: extracted (ADR 0020 §7); a file outside it cannot gain a Portuguese literal, and a file inside it
#: cannot become empty without leaving — the list only shrinks.
PENDING = {
    "src/lib/csv.ts",
    "src/lib/csvImport.ts",
    "src/lib/hierarchy.ts",
    "src/lib/isad.ts",
    "src/lib/quality.ts",
    "src/lib/taxonomy.ts",
    "src/components/description/DescriptionExpansion.tsx",
    "src/components/description/DescriptionPreview.tsx",
    "src/components/description/IsadFieldControl.tsx",
    "src/components/description/Thumbnail.tsx",
    "src/components/hierarchy/MaterialisationPanel.tsx",
    "src/components/ingestion/CsvImportPanel.tsx",
    "src/components/ui/LedgerList.tsx",
    "src/components/ui/Typeahead.tsx",
    "src/components/workers/RunsLedger.tsx",
    "src/components/workers/WorkerOptionsFields.tsx",
    "src/components/workers/WorkerTrialCard.tsx",
    "src/components/workers/WorkersPanel.tsx",
    "src/routes/AnomaliesRoute.tsx",
    "src/routes/BlockedSpellingsRoute.tsx",
    "src/routes/CategoriesRoute.tsx",
    "src/routes/CleaningRulesRoute.tsx",
    "src/routes/CollectionRoute.tsx",
    "src/routes/ConflictsRoute.tsx",
    "src/routes/DeletionsRoute.tsx",
    "src/routes/DiagnosticsRoute.tsx",
    "src/routes/DiscoverRoute.tsx",
    "src/routes/DocumentRoute.tsx",
    "src/routes/EntitiesRoute.tsx",
    "src/routes/InboxRoute.tsx",
    "src/routes/LevelsRoute.tsx",
    "src/routes/NerExclusionsRoute.tsx",
    "src/routes/NewDescriptionRoute.tsx",
    "src/routes/OriginsRoute.tsx",
    "src/routes/PlanRoute.tsx",
    "src/routes/SettingsRoute.tsx",
    "src/routes/SubjectExclusionsRoute.tsx",
    "src/routes/SystemHealthRoute.tsx",
    "src/routes/SystemWorkersRoute.tsx",
    "src/routes/TagsRoute.tsx",
    "src/routes/TextTemplatesRoute.tsx",
    "src/routes/TreeRoute.tsx",
    "src/routes/TypologiesRoute.tsx",
    "src/routes/UsersRoute.tsx",
    "src/routes/VocabularyRoute.tsx",
    "src/routes/WorkerSettingsRoute.tsx",
}


def _portuguese_strings(path: Path) -> list[str]:
    return [
        value
        for value in visible_strings(path)
        # A URL is data, not copy: the attribution's repository address is not a Portuguese word.
        if not value.startswith(("http://", "https://")) and PORTUGUESE.search(value)
    ]


def test_the_extracted_surface_says_no_portuguese() -> None:
    """Everything the catalogue owns is out; the rest is the ratchet, one file at a time."""
    failures: list[str] = []
    for path in SOURCES:
        relative = path.relative_to(CURATOR).as_posix()
        if relative.startswith("src/i18n/") or relative == "src/api/schema.d.ts":
            continue
        values = _portuguese_strings(path)
        if relative in PENDING:
            if not values:
                failures.append(f"{relative} is in PENDING but has no Portuguese left: remove it from the list")
        elif values:
            failures.append(f"{relative} is outside the catalogue and still says Portuguese: {values[:2]}")
    assert not failures, "the interface is extracted file by file (ADR 0020 §7):\n  " + "\n  ".join(failures)


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


#: Routes that only send the browser elsewhere: a path, not a screen.
#:
#: They are listed here instead of in ``lib/screens.ts``, and this table is what makes the exception
#: a line a reviewer reads. The target has to be a declared route, so a redirect cannot survive the
#: screen it pointed at.
REDIRECT_ROUTES: dict[str, str] = {
    "/sistema/ingestao/nova": "/acervo/nova",
    # The ledger became the *Execuções* tab of the operations screen (#207); the old path keeps the
    # bookmarks, the guides and the links inside error states working, filters and all.
    "/sistema/execucoes": "/sistema/workers",
}


def _screen_records() -> dict[str, tuple[str, bool]]:
    """Every entry of `SCREENS`, keyed by its id: its path, and whether its heading is dynamic."""
    body = text(SCREENS).split("export const SCREENS", 1)
    assert len(body) == 2, "`lib/screens.ts` no longer exports `SCREENS`."
    records: dict[str, tuple[str, bool]] = {}
    for block in re.finditer(r"\n  (\w+): \{([^}]*)\}", body[1], re.S):
        identifier, entry = block.group(1), block.group(2)
        path = re.search(r'path:\s*"([^"]+)"', entry)
        assert path, f"`SCREENS.{identifier}` has no path, so no route can be matched to it."
        records[identifier] = (path.group(1), "dynamicTitle: true" in entry)
    assert records, "`lib/screens.ts` declares no screen."
    return records


def _routes() -> dict[str, str | None]:
    """Every route of `router.tsx`, keyed by its path: its component, or ``None`` for a redirect.

    A redirect is a route with no screen: it has a ``beforeLoad`` that throws, not a component. The
    ``None`` is what lets the two catalogue tests below skip it, while ``REDIRECT_ROUTES`` keeps the
    exception visible.
    """
    records: dict[str, str | None] = {}
    for block in re.finditer(r"createRoute\(\{(.*?)\n\}\);", text(ROUTER), re.S):
        entry = block.group(1)
        path = re.search(r'path:\s*"([^"]+)"', entry)
        component = re.search(r"component:\s*(\w+)", entry)
        redirect_to = re.search(r'redirect\(\{\s*to:\s*"([^"]+)"', entry)
        assert path and (component or redirect_to), (
            f"a route in `router.tsx` has no path, or neither a component nor a redirect:\n{entry[:200]}"
        )
        records[path.group(1)] = component.group(1) if component else None
    assert records, "`router.tsx` declares no route."
    return records


def test_every_route_has_a_named_screen() -> None:
    """A route without a name is a screen the menu, the card and the heading cannot agree on."""
    screens = _screen_records()
    routes = _routes()
    redirects = {path for path, component in routes.items() if component is None}
    assert redirects == set(REDIRECT_ROUTES), (
        f"the routes without a component ({sorted(redirects)}) and `REDIRECT_ROUTES` "
        f"({sorted(REDIRECT_ROUTES)}) disagree. A route that only redirects has to be listed in "
        "this gate, and a listed path has to be a redirect in `router.tsx`."
    )
    for source, target in REDIRECT_ROUTES.items():
        assert source in routes, f"`REDIRECT_ROUTES` names {source}, which `router.tsx` does not declare."
        assert target in routes, f"the redirect {source} points at {target}, which `router.tsx` does not declare."
        assert re.search(
            rf'path:\s*"{re.escape(source)}".*?redirect\(\{{\s*to:\s*"{re.escape(target)}"', text(ROUTER), re.S
        ), f"`{source}` is listed as redirecting to `{target}`, but `router.tsx` does not say so."

    named = {path for path, _ in screens.values()}
    routable = set(routes) - redirects
    overlap = sorted(named & redirects)
    assert not overlap, (
        f"`lib/screens.ts` names these redirect paths as screens: {overlap}. A redirect has no "
        "heading, no menu entry and no settings card; the catalogue would point at a dead end."
    )
    missing = sorted(routable - named)
    assert not missing, (
        f"these routes of `apps/curator/src/router.tsx` have no entry in `lib/screens.ts`: {missing}. "
        "Every screen has one name, and it is the one the menu, the settings card and the `<h1>` read."
    )
    orphaned = sorted(named - routable)
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
        if component is None:
            continue
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


def test_the_verdict_and_the_spelling_screen_link_to_each_other() -> None:
    """The two screens of #232 name each other, and by the route rather than by a tab.

    They share a word — *bloqueado* — and half their data: confirming a verdict plants the ban the
    other screen lists. The difference is the object (meaning vs spelling), and the only thing that
    keeps it visible is each screen pointing at the other. The target is read from `SCREENS`, so a
    route rename fails here instead of leaving a button that lands on the old tab — which is what the
    single `Tags` link did before the copy passes: it opened `Relevância`.
    """
    screens = _screen_records()
    verdict_path = screens["subjectExclusions"][0]
    spellings_path = screens["blockedSpellings"][0]

    verdict = SRC / "routes" / "SubjectExclusionsRoute.tsx"
    spellings = SRC / "routes" / "BlockedSpellingsRoute.tsx"
    for source, target, name in (
        (verdict, spellings_path, "the blocked spellings"),
        (spellings, verdict_path, "the verdict"),
    ):
        assert source.exists(), f"#232 moved a screen and `{source.name}` no longer exists."
        assert f'to="{target}"' in text(source), (
            f"`{source.name}` does not link to `{target}` ({name}). The two screens share a "
            "vocabulary, and each one naming the other is what stops them reading as one list with "
            "two filters."
        )

    # A bookmark on the old tab has to reach the new screen: the redirect is the second half of the
    # link, and a validator that forgot the legacy id would answer `Relevância` instead.
    assert re.search(
        rf'path:\s*"{re.escape(screens["tags"][0])}".*?throw redirect\(\{{\s*to:\s*"{re.escape(spellings_path)}"',
        text(ROUTER),
        re.S,
    ), (
        "`?aba=stopwords` no longer reaches the blocked-spellings screen. The tags route redirects "
        f"it to `{spellings_path}` in `beforeLoad`, and `LEGACY_ABAS` keeps the id accepted so the "
        "redirect can see it."
    )

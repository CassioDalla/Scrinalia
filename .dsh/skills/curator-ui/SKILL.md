---
name: curator-ui
description: "The curator SPA: Tailwind v4 token syntax, the generated client as the only API seam, the permission mirror and the screens."
whenToUse: "When changing anything under apps/curator."
---

# curator-ui

## Render before you call it verified

- **A change that touches a screen is not verified until the screen is rendered and the screenshot
  shown.** `tsc`, ESLint and the Vite build were green while 105 bracket-form tokens rendered nothing,
  and the same gates were green again while this was only a sentence: the pixels are the one evidence
  that the tokens resolve, the copy fits the real header and the new control is where the archivist
  looks. Load the `render` rule file for the procedure — check that a headless shell exists, launch it,
  drive it with CDP if the screen needs a session, and inspect the PNG with `read_image`.
- **When it cannot be rendered, say so in the terms `docs/log.md` uses**: "not looked at in a browser;
  the evidence is `tsc`, ESLint, the Vite build". Never describe a screen you did not see, and never
  imply pixels from a green build. A missing browser is a property of the machine, not a broken UI.

## Tokens and the generated client

- Tailwind v4 tokens are used with **parentheses**, not brackets: `bg-(--color-surface)`, `text-(--color-muted)`, `ring-(--color-line)`. The bracket form `bg-[--color-surface]` compiles to `background-color:--color-surface`, which is invalid CSS that the browser drops **silently** — the build stays green and the theme simply does not apply. This shipped once (105 occurrences) and was only caught by rendering the screens; when touching the UI, look at the page, do not trust a green `tsc`/`eslint`/`vite build`.
- The front talks to the API only through the generated client (`apps/curator/src/api/client.ts`, `openapi-fetch`); it never queries Postgres and never builds a URL by hand. Keep it that way — the API is the contract, and it is the one thing both surfaces (curator today, public site next) share.
- **A query shape is derived from the route, never typed out.** `params: NonNullable<paths["<route>"]["get"]["parameters"]["query"]>`, or a named alias doing exactly that. A hand-written filter object is a second definition of what the API accepts, and it fails in the direction nothing catches: measured, an unknown query parameter is *ignored* and the route answers 200 with the whole set — `?is_anomaly=true` filters 28 of 101, `?is_anomalyy=true` and `?non_sense=42` both answer 101 — so a mirror that lost a key, or a contract that renamed one, leaves the screen filtering by nothing while its chip says it filtered, with `tsc`, ESLint, the build and the suite green. It happened: `DocumentSearch` had lost `is_anomaly` and survived only because `CollectionRoute.toRequest` spreads a wider type into it. `testing/unit/curator/test_api_query_shapes.py` fails on the next one. The generated type already spells an omitted filter `campo?: T | null`, so the derivation needs no mapping and no `Exclude`.
- **A request body is derived from the model the route declares, never typed out.** `body: MergeBatchRequest`, where the alias is `components["schemas"]["MergeBatchRequest"]`; a deliberate narrowing is a `Pick`/`Omit`/`Required` **over that model**, with the screen or the route that justifies it named beside it. This is the mirror image of the query failure: measured, pydantic refuses a **required** field that is renamed or missing (the route answers 400) and *ignores* an **optional** one and an unknown one (200) — `EntityMergePreviewRequest` with `new_name` renamed to `new_nam` validates, and the merge simply does not rename — so a hand-written body loses the optional half without a trace. The silence is not even uniform: ten of the thirteen request models keep pydantic's `extra="ignore"` and three forbid it, so the client must not learn the list by copying it (#177). `testing/unit/curator/test_api_body_shapes.py` fails on the next literal **and** on the next narrowing that is not in its table, and the narrowing still derives, so a rename in the contract is a compile error.

## Um hint, e só um

- **`components/ui/Hint.tsx` é a única explicação discreta.** O gatilho padrão é um `<button>` só
  com ícone `Info`, nomeado por `label`; quando o gatilho já é um controle — uma aba —, passa-se
  `asChild` e o próprio botão vira o gatilho. O painel é `role="tooltip"` com `aria-describedby`, o
  texto fica no DOM (`sr-only` fechado), abre no hover e no foco, alterna no clique/toque, fecha no
  Escape e no ponteiro fora. O comportamento está pinado em
  `apps/curator/tests/hint.test.tsx`; o DOM dos testes vem de `happy-dom` + Testing Library,
  registrado no `apps/curator/bunfig.toml`.
- **Hint é secundário, nunca a única descrição.** Instrução para preencher um campo, ação
  destrutiva e regra de governança continuam visíveis: `Field.hint` embaixo do controle, `Notice` ou
  `Disclosure` quando é um parágrafo. Tooltip não carrega link, botão nem campo — quando o texto
  precisa disso, o componente é `Disclosure`, não `Hint`.
- **`Field.info` é o slot ao lado do rótulo, fora do `<label>`.** Um `<button>` dentro de `<label>`
  é HTML inválido e contamina o nome acessível do input; o `Field` renderiza o `info` como irmão do
  label. Não criar um `hintMode` que esconda o `hint` visível.
- **O `title` nativo se aposenta como explicação a cada uso migrado.** Ele sobrevive onde o texto
  não é a única forma de saber — truncamento, valor completo de uma célula, o nome de um ícone — e
  não é o padrão "discreto" da interface.
- **O painel é posicionado com `absolute`, sem portal.** Um ancestral com `overflow: auto/hidden`
  recorta o tooltip: os usos atuais não têm esse ancestral. Se um lugar precisar de colisão real,
  isso é uma decisão sobre Floating UI, não um `z-index` maior.

## Editing copy: click the element, land on the line

- **Alt+right-click** an element on a screen opened through `bun run curator:dev` and the plugin
  (`vite-plugin-react-click-to-component`, wired in `apps/curator/vite.config.ts`) opens that
  element's file and line in the editor — which is the gesture a **copy** pass wants, because the
  string is on the line, not on the component's definition.
- **It only works against the dev server.** The production transform emits no `jsxDEV` at all
  (measured: 0 `fileName`, 0 `lineNumber` in `dist/`), so a built SPA served by the API answers
  nothing — and a browser extension that reads the source off the fiber finds nothing **even in
  dev**, because React 19 dropped the `source` argument from `jsxDEV`
  (`ReactElement(type, key, props, owner, debugStack, debugTask)`, `_debugInfo` fixed at `null`).
  The plugin is the one that threads it back by patching the dev runtime. Both facts were measured;
  do not "fix" a non-working inspector by adding source maps.
- The plugin is dev-only by construction (`config.command === "serve"` in every hook) and the built
  bundle carries nothing of it. It is deliberately **not** a component gallery (Ladle, a `/dev`
  route): the unit of this interface is the screen with real data, and a sentence that fits a
  gallery's 200px can wrap to three lines in a real header.
- Copy is not only in `src/routes/`: `src/components/hierarchy/MaterialisationPanel.tsx` kept saying
  `rung`, `apply` and `dry-run` through a whole review pass because it is a component and not a
  screen. `testing/unit/curator/test_curator_copy.py` now fails on the retired words, so the next
  one is caught by the suite instead of by a reader.


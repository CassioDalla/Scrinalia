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


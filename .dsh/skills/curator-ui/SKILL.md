---
name: curator-ui
description: "The curator SPA: Tailwind v4 token syntax, the generated client as the only API seam, the permission mirror and the screens."
whenToUse: "When changing anything under apps/curator."
---

# curator-ui

## Tokens and the generated client

- Tailwind v4 tokens are used with **parentheses**, not brackets: `bg-(--color-surface)`, `text-(--color-muted)`, `ring-(--color-line)`. The bracket form `bg-[--color-surface]` compiles to `background-color:--color-surface`, which is invalid CSS that the browser drops **silently** — the build stays green and the theme simply does not apply. This shipped once (105 occurrences) and was only caught by rendering the screens; when touching the UI, look at the page, do not trust a green `tsc`/`eslint`/`vite build`.
- The front talks to the API only through the generated client (`apps/curator/src/api/client.ts`, `openapi-fetch`); it never queries Postgres and never builds a URL by hand. Keep it that way — the API is the contract, and it is the one thing both surfaces (curator today, public site next) share.

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


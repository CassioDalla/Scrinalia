---
name: curator-ui
description: "The curator SPA: Tailwind v4 token syntax, the generated client as the only API seam, the permission mirror and the screens."
whenToUse: "When changing anything under apps/curator."
---

# curator-ui

## Tokens and the generated client

- Tailwind v4 tokens are used with **parentheses**, not brackets: `bg-(--color-surface)`, `text-(--color-muted)`, `ring-(--color-line)`. The bracket form `bg-[--color-surface]` compiles to `background-color:--color-surface`, which is invalid CSS that the browser drops **silently** — the build stays green and the theme simply does not apply. This shipped once (105 occurrences) and was only caught by rendering the screens; when touching the UI, look at the page, do not trust a green `tsc`/`eslint`/`vite build`.
- The front talks to the API only through the generated client (`apps/curator/src/api/client.ts`, `openapi-fetch`); it never queries Postgres and never builds a URL by hand. Keep it that way — the API is the contract, and it is the one thing both surfaces (curator today, public site next) share.


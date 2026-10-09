---
name: render
description: "Render and screenshot the curator SPA in an environment where no browser is a project dependency: check whether a Playwright browser exists, launch the headless shell that renders, and report honestly when pixels are impossible. Use when a change touches the UI, when a screenshot is requested, or before claiming a screen was verified."
whenToUse: "When a change touches the curator UI, when the user asks for a print of a screen, or before claiming that a screen was looked at."
---

# Render

## Ground rules

- **No browser is a dependency of this repository.** `playwright` is absent from `package.json`,
  `apps/curator/package.json` and `pyproject.toml`, and neither `bun.lock` nor `uv.lock` carries it:
  `bun install` and `uv sync` download no browser, and no CI job renders. The browsers under
  `~/.cache/ms-playwright/` belong to **other checkouts on the machine** — the cache's `.links/`
  files name the `node_modules/playwright-core` that put each one there. Whether a session can render
  is therefore a property of the machine, not of the clone, and **it changes from session to
  session**: do not read a missing browser as a broken UI, and do not add Playwright to the repo to
  "fix" it — a browser download on every install is a decision, not a side effect.
- **Check first.** `ls ~/.cache/ms-playwright/` answers whether rendering is possible at all. Empty
  or absent means there is no browser, and the honest report is that the screen was **not looked at**
  (see *When rendering is impossible*).
- **Launch the headless shell, not the full Chrome.** What renders here is
  `chromium_headless_shell-<n>/chrome-headless-shell-linux64/chrome-headless-shell`. The full
  `chromium-<n>/chrome-linux64/chrome` that `playwright-core` launches **dumps core before
  rendering** — `SIGTRAP`, under `--headless=old` and `--headless=new` alike, the failure
  `docs/log.md` records as "headless Chromium in this environment dumps core before rendering".

## Recipe

```sh
shell=$(ls -d ~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell | sort -V | tail -1)
"$shell" --no-sandbox --disable-gpu --hide-scrollbars --virtual-time-budget=6000 \
  --user-data-dir=.render/profile --window-size=1280,900 --screenshot=.render/screen.png <url>
```

Measured: that command renders the built SPA (below) as a 1280×900 PNG of the login screen.

- **The profile directory goes inside the workspace, never `/tmp`.** `/tmp` is a private tmpfs per
  command in this environment — anything written there is gone before the next command — so a profile
  kept there cannot outlive the call that started the browser.
- The URL can be the built SPA served statically, which needs no API and still renders the real
  shell:

  ```sh
  python3 -m http.server 8791 --directory apps/curator/dist &
  # ... the same command as above, with http://127.0.0.1:8791/ as the url, then kill the server
  ```

  With the dev stack up, `http://localhost:5173/<route>` renders the live screens instead (the Vite
  proxy answers 502 on `/api` without the API, which the SPA shows as its own error state).
- `--virtual-time-budget=<ms>` lets the SPA boot before the shot. `--remote-debugging-port=<port>`
  plus CDP is how a script clicks and navigates; a Python CDP driver imports `websockets`, which
  reaches the venv only as an extra of `uvicorn[standard]` — present by accident, not by declaration.
- Inspect the result with the `read_image` tool, and **delete the profile and any throwaway script
  when done**: this repo keeps no `scripts/` (see `AGENTS.md`).

## When rendering is impossible

- A green `tsc`/`eslint`/`vite build` is **not** a rendered screen: the bracket-form Tailwind tokens
  (`bg-[--color-surface]`) shipped 105 times with every gate green, and only the page showed it. The
  same holds for a missing browser.
- Say it in the terms `docs/log.md` already uses: the evidence is `tsc`, ESLint, the build and the
  bundle's text, and the screen was simply **not looked at**. Never describe a screen you did not see
  and never imply pixels from a green build.

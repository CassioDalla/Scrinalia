"""The files the documentation site draws with, and the identity they cannot drift from.

Two things can go wrong with an asset `mkdocs.yml` names, and **neither one fails the build**:

* **a path that does not exist.** Measured: `mkdocs build --strict` exits 0 with `theme.logo`,
  `theme.favicon` and `extra_css` all pointing at files that are not there — the strict build fails
  on a broken *link*, not on a missing *asset*. So a typo here ships a site with no mark and every
  gate green, which is exactly the class of defect this test exists for;
* **a copy that drifts.** The mark, the favicon and the brand serif live once, in the curator
  (`apps/curator/`); they are copied into `docs/assets/` because the SPA's Vite root and the
  documentation root do not share a build, and a symlink across them would break on a Windows
  checkout. A copy is a second definition, so it is pinned to the first: the day the identity moves,
  this fails until the documentation copy moves with it.

The stylesheet is held the same way, against the tokens themselves: the values are read out of
`apps/curator/src/styles.css`, not repeated here, so this test cannot agree with the documentation
while disagreeing with the curator.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs"
CONFIG = REPO_ROOT / "mkdocs.yml"

CURATOR_CSS = "apps/curator/src/styles.css"
DOCS_CSS = "assets/stylesheets/scrinalia.css"

#: The assets `mkdocs.yml` names, and where each one comes from — `None` for the documentation's own.
#: The partition is exact in both directions: an asset added to the configuration without a line here
#: fails `test_every_named_asset_is_declared`, so the identity cannot grow a fourth drawing by
#: accident.
THEME_ASSETS: dict[str, str | None] = {
    "assets/brand/mark.svg": "apps/curator/src/assets/brand/marca-escura.svg",
    "assets/brand/favicon.svg": "apps/curator/public/favicon.svg",
    "assets/stylesheets/scrinalia.css": None,
}

#: The files that are copies of a curator file but are not named by the configuration — the font the
#: stylesheet reaches for, and the licence OFL-1.1 requires to travel beside it. Every entry here is
#: pinned byte for byte, the same way the two above are.
ASSET_COPIES: dict[str, str] = {
    "assets/fonts/pt-serif-400.woff2": "apps/curator/src/assets/fonts/pt-serif-400.woff2",
    "assets/fonts/OFL.txt": "apps/curator/src/assets/fonts/OFL.txt",
}

#: The tokens the stylesheet must carry, named as the curator names them. The rail is not here: the
#: curator keeps it as `oklch(0.238 0.027 247)` and the docs stylesheet uses the identity's own hex,
#: `#14202b`, which is the same colour (measured by conversion) in the form the identity files state
#: it.
SHARED_TOKENS = ("--color-paper", "--color-ink", "--color-accent", "--color-rail-ink")

_TOKEN = re.compile(r"^\s*(--color-[a-z-]+):\s*(.+?);", re.MULTILINE)
_URL = re.compile(r"""url\(\s*["']?(?P<target>[^"')]+)["']?\s*\)""")


def site_config() -> dict:
    """`mkdocs.yml`, read by a YAML parser and not by a second one of ours."""
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def named_assets() -> set[str]:
    """Every asset path the configuration hands to the theme."""
    config = site_config()
    theme = config["theme"]
    named = {theme.get("logo"), theme.get("favicon")}
    named |= set(config.get("extra_css") or [])
    named |= set(config.get("extra_javascript") or [])
    named.discard(None)
    return named


def curator_tokens() -> dict[str, str]:
    """Every `--color-*` the curator's `@theme` block defines, value verbatim."""
    return dict(_TOKEN.findall((REPO_ROOT / CURATOR_CSS).read_text(encoding="utf-8")))


def test_the_documentation_site_names_the_identity() -> None:
    theme = site_config()["theme"]
    assert theme.get("logo") == "assets/brand/mark.svg", "the header logo is the identity's mark"
    assert theme.get("favicon") == "assets/brand/favicon.svg", (
        "the favicon is the file the SPA itself serves (`apps/curator/public/favicon.svg`), not a "
        "second drawing of the mark"
    )
    assert theme.get("font") is False, (
        "Material fetches Roboto from Google Fonts unless `font: false`. The site draws its own "
        "wordmark from a self-hosted file, like the SPA: a page that reaches a third party to draw "
        "its own name draws nothing when that party is unreachable"
    )


def test_every_named_asset_is_declared() -> None:
    """No asset arrives without a line saying whether it is a copy, and of what."""
    unpinned = sorted(named_assets() - set(THEME_ASSETS))
    assert not unpinned, (
        f"`mkdocs.yml` serves {unpinned}, which this test does not declare. An asset that is not a "
        "copy of a curator file is a second definition of the identity: add it to THEME_ASSETS with "
        "the file it comes from (or `None`, if the documentation owns it)"
    )
    unused = sorted(set(THEME_ASSETS) - named_assets())
    assert not unused, f"THEME_ASSETS declares {unused}, which `mkdocs.yml` no longer serves"


def test_every_asset_exists_under_docs() -> None:
    for asset in (*THEME_ASSETS, *ASSET_COPIES):
        assert (DOCS / asset).is_file(), (
            f"`docs/{asset}` does not exist, so the site serves nothing there. `--strict` does not "
            "catch this: measured, a build with a missing logo, favicon and stylesheet exits 0"
        )


def test_the_copies_are_the_curator_files() -> None:
    """Byte for byte, because a copy that is *almost* the identity is the drift this pins."""
    pairs = {**{k: v for k, v in THEME_ASSETS.items() if v}, **ASSET_COPIES}
    assert pairs, "no asset is pinned to a curator file any more; the identity copy is unpinned"
    for asset, source in pairs.items():
        original = REPO_ROOT / source
        assert original.is_file(), f"`{source}` is gone; the identity moved and this pair is stale"
        assert (DOCS / asset).read_bytes() == original.read_bytes(), (
            f"`docs/{asset}` is not byte-identical to `{source}`. The site copies the identity "
            "rather than defining a second one — re-copy the file, then re-render the site"
        )


def test_every_file_the_stylesheet_reaches_for_exists() -> None:
    """A `url(...)` in the stylesheet is a second way to name a missing file, and the build is blind
    to it too: the font would silently fall back and the wordmark would lose its serif."""
    stylesheet = DOCS / DOCS_CSS
    references = [target for target in _URL.findall(stylesheet.read_text(encoding="utf-8")) if "://" not in target]
    assert references, "the stylesheet reaches for nothing; the brand serif is not being loaded"
    for target in references:
        resolved = (stylesheet.parent / target).resolve()
        assert resolved.is_relative_to(DOCS.resolve()), (
            f"`{target}` resolves outside `docs/`, where MkDocs would not copy it into the site"
        )
        assert resolved.is_file(), f"`{target}` does not exist, so the browser fetches a 404"


def test_the_stylesheet_uses_the_curators_tokens() -> None:
    """The values, taken from the curator's own stylesheet: no palette is repeated in this test."""
    tokens = curator_tokens()
    css = (DOCS / DOCS_CSS).read_text(encoding="utf-8")
    for name in SHARED_TOKENS:
        value = tokens.get(name)
        assert value, f"`{CURATOR_CSS}` no longer defines `{name}`; the pair this test pins moved"
        assert value in css, (
            f"`docs/{DOCS_CSS}` does not use `{name}: {value}` from `{CURATOR_CSS}`. The "
            "documentation site draws with the curator's tokens; if the identity changed, change "
            "both — and if the documentation deliberately stops using this one, drop it from "
            "SHARED_TOKENS in the same diff"
        )

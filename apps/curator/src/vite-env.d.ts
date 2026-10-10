/// <reference types="vite/client" />

/**
 * The system's version, replaced at build time by `vite.config.ts` from `pyproject.toml`.
 *
 * It is a `define` and not a request: the built SPA is served by the API from the same commit, so
 * the number is known when the bundle is written. `PRODUCT.version` in `lib/copy.ts` is the only
 * reader, and `AttributionFooter` is the only screen that shows it.
 */
declare const __APP_VERSION__: string;

/**
 * The tags screen's copy (ADR 0020 §7). The section is merged into `pages` by `i18n/pt.ts` and
 * `i18n/en.ts`; keeping it in its own module is what lets the screen be extracted without touching
 * the central catalogue.
 */

export const pt = {} as const;

export const en: typeof pt = {};

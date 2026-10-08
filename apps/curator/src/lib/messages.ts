/**
 * The one place where a route's answer becomes text on the screen.
 *
 * Every write route answers `code` plus `message`: the code is the identity of the outcome, and the
 * sentence is the Portuguese the API still composes. The screens used to print `message` directly,
 * which meant that translating the interface later would leave every confirmation and every refusal
 * in the server's language — thirteen call sites with no seam to change.
 *
 * This is the seam. Today the catalogue is empty and the sentence passes through unchanged, so
 * nothing the archivist reads has moved. Filling `TRANSLATIONS` is what turns the interface
 * multilingual, and no screen has to be touched to do it.
 *
 * A code with no entry falls back to `message` on purpose: a route that adds an outcome must not
 * render an empty line in a client that does not know it yet. That is also why the API keeps
 * sending the sentence.
 */

import type { components } from "@/api/schema";

/** The outcomes the API can report. Generated from the contract, so it cannot drift. */
export type RouteMessageCode = components["schemas"]["RouteMessageCode"];

/**
 * Translations by outcome, for the day the interface stops being Portuguese-only.
 *
 * Deliberately empty: the product is Portuguese today, and inventing entries now would be a
 * translation nobody reviewed. The map exists so that the day it is filled, the screens already
 * read from it.
 */
const TRANSLATIONS: Partial<Record<RouteMessageCode, string>> = {};

/**
 * What to show for a route answer: the translation when there is one, the API's sentence otherwise.
 *
 * Accepts an optional code and an optional message because the clustering route succeeds with an
 * empty answer — its sentence is a warning, not a confirmation, and it is absent on the happy path.
 */
export function routeMessage(response: { code?: RouteMessageCode | null; message?: string | null }): string {
  const translated = response.code ? TRANSLATIONS[response.code] : undefined;

  return translated ?? response.message ?? "";
}

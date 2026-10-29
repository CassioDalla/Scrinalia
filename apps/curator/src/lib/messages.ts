/**
 * The one place where a route's answer becomes text on the screen.
 *
 * Every write route answers `code` plus `message`: the code is the identity of the outcome and the
 * sentence is composed by the API in the request's language (ADR 0020 §4). The screens read through
 * here instead of reaching for `.message`, so a later change of channel — a client-side rendering of
 * an outcome — has one seam to change and twelve call sites do not have to move.
 *
 * The sentence is never translated on this side: the API already sent the language the request asked
 * for, and a second catalogue here would be a second definition of the same words.
 */

import type { components } from "@/api/schema";

/** The outcomes the API can report. Generated from the contract, so it cannot drift. */
export type RouteMessageCode = components["schemas"]["RouteMessageCode"];

/**
 * What to show for a route answer.
 *
 * Accepts an optional code and an optional message because the clustering route succeeds with an
 * empty answer — its sentence is a warning, not a confirmation, and it is absent on the happy path.
 */
export function routeMessage(response: { code?: RouteMessageCode | null; message?: string | null }): string {
  return response.message ?? "";
}

/**
 * The sentence for a refusal: the API's, already in the request's language.
 *
 * Accepts the shape `ApiError` already has, so a screen passes the error itself.
 */
export function refusalMessage(error: { code?: string | null; message?: string | null }): string {
  return error.message ?? "";
}

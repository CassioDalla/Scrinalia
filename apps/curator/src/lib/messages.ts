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

/**
 * What to show for a **refusal**, keyed by the API's ``error_code``.
 *
 * The other half of the same seam. A refusal carries a code, a Portuguese sentence, and — when it has
 * facts to state — a ``details`` payload with them. This is where the sentence the archivist reads is
 * composed: the server's prose is the fallback for a code this catalogue does not know yet, exactly as
 * `routeMessage` falls back to `message`, so a refusal added later is never an empty line.
 *
 * Why a second map instead of one: the two channels are different in the API. `routeMessage` is keyed
 * by `RouteMessageCode`, an enum the contract generates; a refusal is keyed by the exception's class
 * name, which the contract does not carry. Merging them would mean typing an enum that does not exist.
 */
const REFUSALS: Partial<Record<string, (details: RefusalDetails) => string>> = {
  /**
   * A rename onto a spelling another entity already carries. The twin travels in ``details`` because
   * a translated interface cannot interpolate a fact out of the server's sentence, and the archivist
   * needs to read *which* name collided — the answer to the collision is the merge card, and it takes
   * both names.
   */
  DuplicateEntityNameError: (details) => {
    const twin = details?.conflicting_entity as { name?: string } | undefined;
    return twin?.name
      ? `Já existe uma entidade chamada "${twin.name}". Mescle as duas em vez de renomear.`
      : "Já existe uma entidade com essa grafia. Mescle as duas em vez de renomear.";
  },
};

/** The facts a refusal carries, when it carries any. */
export type RefusalDetails = Record<string, unknown> | undefined;

/**
 * The sentence for a refusal: this catalogue's copy when it knows the code, the API's otherwise.
 *
 * Accepts the shape `ApiError` already has, so a screen passes the error itself and never reaches for
 * `.message` — which is the call site that would freeze the server's language into the interface.
 */
export function refusalMessage(error: {
  code?: string | null;
  message?: string | null;
  details?: RefusalDetails;
}): string {
  const render = error.code ? REFUSALS[error.code] : undefined;

  return render?.(error.details) ?? error.message ?? "";
}

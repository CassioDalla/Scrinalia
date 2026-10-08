/**
 * Coercions for the values that travel in the route search.
 *
 * A search parameter reaches ``validateSearch`` in two different shapes, and a validator that only
 * accepts one of them **erases the other**:
 *
 * * from the address bar it arrives as a string (``"12"``, ``"true"``), because that is what a URL
 *   carries;
 * * from ``navigate({ search })`` it arrives as the object the screen wrote, so a number stays a
 *   number and a boolean stays a boolean — TanStack Router runs ``validateSearch`` on the
 *   destination object before serialising it.
 *
 * The second case is the one that shipped broken: a validator written as ``typeof value === "string"
 * ? Number(value) : undefined`` answered ``undefined`` for the number the screen had just handed it,
 * and because the validator's result is spread over the destination, it *overwrote* the value with
 * ``undefined``. Clicking a collection facet therefore did nothing at all — the filter was dropped
 * between the click and the request — while ``entity_type`` survived, since it travels as a string.
 * The same defect silently disabled the pagination of the merge proposals, the diagnostics, the
 * anomalies, the similarities and the conflicts screens.
 *
 * So these helpers accept both shapes. They are the only place in the front that decides what a
 * search value means; a route validator that hand-rolls the check again is a route that will lose a
 * filter again.
 */

/** A string, from the URL or from a screen, ignoring the empty one. */
export function asString(value: unknown): string | undefined {
  if (typeof value === "string") return value.length > 0 ? value : undefined;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return undefined;
}

/** A finite number, from either ``"12"`` or ``12``. */
export function asNumber(value: unknown): number | undefined {
  if (typeof value === "number") return Number.isFinite(value) ? value : undefined;
  if (typeof value === "string" && value.length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

/**
 * A boolean, from ``true``, ``"true"``, ``false`` or ``"false"``.
 *
 * Anything else is "not set" rather than "false": an absent filter and a filter turned off are the
 * same state, and answering ``false`` for garbage would put a hidden filter on the query.
 */
export function asBoolean(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

/**
 * One of a closed vocabulary, so the screen can never send a value the route refuses.
 *
 * The allowed list belongs to the API (it is read from the contract); this only narrows an unknown
 * value to it.
 */
export function asEnum<T extends string>(value: unknown, allowed: readonly T[]): T | undefined {
  const text = asString(value);
  return text !== undefined && (allowed as readonly string[]).includes(text) ? (text as T) : undefined;
}

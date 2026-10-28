import type { components } from "@/api/schema";

import { en } from "./en";
import { pt, type Messages } from "./pt";

/** The two locales of the interface (ADR 0020), generated from the contract. */
export type Locale = components["schemas"]["Locale"];

export const LOCALES: readonly Locale[] = ["pt-BR", "en"];

/** A language names itself; "Automático"/"Automatic" is the only translatable one. */
export const LOCALE_LABEL: Record<Locale, string> = { "pt-BR": "Português", en: "English" };

/** What an unsupported browser language falls back to: the product's own voice. */
export const DEFAULT_LOCALE: Locale = "pt-BR";

export const CATALOGUES: Record<Locale, Messages> = { "pt-BR": pt, en };

/** The key the choice is remembered under, until the account carries it (ADR 0020 §3). */
const STORAGE_KEY = "scrinalia.curator.locale";

export function isLocale(value: unknown): value is Locale {
  return value === "pt-BR" || value === "en";
}

/**
 * The locale a browser language asks for, or the default.
 *
 * `pt-PT` is Portuguese and reads the same catalogue; anything that is neither `pt*` nor `en*` gets
 * the product's default rather than a half-understood interface.
 */
export function detectLocale(language: string | undefined = globalThis.navigator?.language): Locale {
  const tag = (language ?? "").trim().toLowerCase();
  if (tag.startsWith("pt")) return "pt-BR";
  if (tag.startsWith("en")) return "en";
  return DEFAULT_LOCALE;
}

function readStored(): Locale | null {
  try {
    const value = globalThis.localStorage?.getItem(STORAGE_KEY);
    return isLocale(value) ? value : null;
  } catch {
    // A browser that refuses storage still gets an interface; it just cannot remember the choice.
    return null;
  }
}

let active: Locale = readStored() ?? detectLocale();

/**
 * The locale the non-React modules format in.
 *
 * `format.ts` and the API client are plain functions, called from everywhere; making them take a
 * locale would thread a parameter through 220 call sites. The provider keeps this variable in step
 * with the context before it re-renders, so a render always formats in the locale it draws.
 */
export function activeLocale(): Locale {
  return active;
}

export function activeMessages(): Messages {
  return CATALOGUES[active];
}

export function messagesFor(locale: Locale): Messages {
  return CATALOGUES[locale];
}

/**
 * Sets the module locale. `persist` is false when the account is the source of the choice: the
 * storage belongs to the anonymous phase, and a signed-in account must not inherit the previous
 * person's language from this browser (ADR 0020 §3).
 */
export function setActiveLocale(locale: Locale, persist = true): void {
  active = locale;
  if (!persist) return;
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, locale);
  } catch {
    // See `readStored`.
  }
}

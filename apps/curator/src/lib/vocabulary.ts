/**
 * Portuguese labels for the collection-vocabulary codes.
 *
 * Only text lives here: the kinds (``DISTRICT``/``MUNICIPALITY``/…) are the contract's, and the
 * list the screen iterates comes from the API's own enum — the front must not carry a second copy
 * of it, or a kind added on the back-end would render as a raw code.
 */

import { activeMessages } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";
import type { BadgeTone } from "@/lib/hierarchy";

type TermKind = keyof Messages["vocabulary"]["termKind"];

function termKindField(field: "label" | "hint"): Record<string, string> {
  return new Proxy({} as Record<string, string>, {
    get(_target, key) {
      const kind = String(key) as TermKind;
      return activeMessages().vocabulary.termKind[kind]?.[field] ?? (field === "label" ? String(key) : "");
    },
  });
}

export const TERM_KIND_LABEL = termKindField("label");

export const TERM_KIND_TONE: Record<string, BadgeTone> = {
  DISTRICT: "accent",
  MUNICIPALITY: "accent",
  STATE: "warn",
  REGION: "warn",
  COUNTRY: "neutral",
  PERSON: "ok",
};

/**
 * What each kind decides, which is the whole point of the catalogue.
 *
 * A place kind is refused by the subject axis *and* carried by the entity axis (``LOC``), which is
 * what search and diffusion read. ``PERSON`` is the producer (``PER``), and that is the same
 * reasoning that retired the ``Pessoa`` drawer. A screen that did not distinguish the two would make
 * "não é assunto" look like "não serve para nada" (ADR 0013).
 */
export const TERM_KIND_HINT = termKindField("hint");

/** The kind label, falling back to the raw code so a new kind is visible instead of blank. */
export function termKindLabel(kind: string): string {
  return TERM_KIND_LABEL[kind] ?? kind;
}

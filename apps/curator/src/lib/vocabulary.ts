/**
 * Portuguese labels for the collection-vocabulary codes.
 *
 * Only text lives here: the kinds (``DISTRICT``/``MUNICIPALITY``/…) are the contract's, and the
 * list the screen iterates comes from the API's own enum — the front must not carry a second copy
 * of it, or a kind added on the back-end would render as a raw code.
 */

import type { BadgeTone } from "@/lib/hierarchy";

export const TERM_KIND_LABEL: Record<string, string> = {
  DISTRICT: "Bairro",
  MUNICIPALITY: "Município",
  STATE: "Estado",
  REGION: "Região",
  COUNTRY: "País",
  PERSON: "Pessoa",
};

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
 * A place kind claims the ``PLACE`` facet — the term is refused by the subject axis *and* kept
 * somewhere. ``PERSON`` goes nowhere: the name is the producer, and that is the same reasoning that
 * retired the ``Pessoa`` drawer. A screen that did not distinguish the two would make "não é
 * assunto" look like "não serve para nada".
 */
export const TERM_KIND_HINT: Record<string, string> = {
  DISTRICT: "Um bairro: o lugar mais fino que a faceta distingue. Vai para a faceta Lugar.",
  MUNICIPALITY: "Um município (inclusive uma cidade estrangeira). Vai para a faceta Lugar.",
  STATE: "Um estado ou província. Vai para a faceta Lugar.",
  REGION: "Uma região mais ampla que um município. Vai para a faceta Lugar.",
  COUNTRY: "Um país que os registros do acervo alcançam. Vai para a faceta Lugar.",
  PERSON: "Um nome de pessoa: o produtor ou a pessoa retratada, nunca um assunto.",
};

/** The kind label, falling back to the raw code so a new kind is visible instead of blank. */
export function termKindLabel(kind: string): string {
  return TERM_KIND_LABEL[kind] ?? kind;
}

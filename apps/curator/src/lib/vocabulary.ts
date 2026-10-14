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
 * A place kind is refused by the subject axis *and* carried by the entity axis (``LOC``), which is
 * what search and diffusion read. ``PERSON`` is the producer (``PER``), and that is the same
 * reasoning that retired the ``Pessoa`` drawer. A screen that did not distinguish the two would make
 * "não é assunto" look like "não serve para nada" (ADR 0013).
 */
export const TERM_KIND_HINT: Record<string, string> = {
  DISTRICT: "Um bairro: o lugar mais fino que a coleção distingue. O eixo de entidades (LOC) o carrega.",
  MUNICIPALITY: "Um município (inclusive uma cidade estrangeira). O eixo de entidades (LOC) o carrega.",
  STATE: "Um estado ou província. O eixo de entidades (LOC) o carrega.",
  REGION: "Uma região mais ampla que um município. O eixo de entidades (LOC) o carrega.",
  COUNTRY: "Um país que os registros do acervo alcançam. O eixo de entidades (LOC) o carrega.",
  PERSON: "Um nome de pessoa: o produtor ou a pessoa retratada, nunca um assunto.",
};

/** The kind label, falling back to the raw code so a new kind is visible instead of blank. */
export function termKindLabel(kind: string): string {
  return TERM_KIND_LABEL[kind] ?? kind;
}

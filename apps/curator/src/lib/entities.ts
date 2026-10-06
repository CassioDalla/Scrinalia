/**
 * Portuguese labels for the named-entity codes.
 *
 * Only text lives here: the codes (``PER``/``ORG``/``LOC``, ``JUDGE``/``HUMAN``, ``TAG``/``ENTITY``)
 * are the contract's, and the entity types the screens iterate come from the API's own enum.
 */

import type { BadgeTone } from "@/lib/hierarchy";

export const ENTITY_TYPE_LABEL: Record<string, string> = {
  PER: "Pessoa",
  ORG: "Organização",
  LOC: "Local",
};

export const ENTITY_TYPE_TONE: Record<string, BadgeTone> = {
  PER: "accent",
  ORG: "ok",
  LOC: "warn",
};

export const ENTITY_TYPE_HINT: Record<string, string> = {
  PER: "Nomes de pessoas, inclusive o autor de um documento.",
  ORG: "Instituições, empresas e órgãos produtores.",
  LOC: "Lugares: logradouros, bairros, rios e edificações.",
};

/** Who recorded a NER veto: the conflict judge, or an archivist. */
export const EXCLUSION_SOURCE_LABEL: Record<string, string> = {
  JUDGE: "juiz LLM",
  HUMAN: "curadoria",
};

/**
 * The two directions of the bidirectional governance.
 *
 * This is the detail the screen exists to make visible: a veto written here is a *curation
 * decision*, and it is stored apart from the subject-axis stopwords on purpose. Collapsing the two
 * would let a NER veto reach the subject purge, which deletes tags.
 */
export const EXCLUSION_SOURCE_HINT: Record<string, string> = {
  JUDGE: "O juiz de conflitos concluiu que a grafia pertence ao eixo de assunto, não a nomes próprios.",
  HUMAN: "Um arquivista decidiu que o termo é assunto; a tag que justifica a decisão fica registrada.",
};

export const CONFLICT_WINNER_LABEL: Record<string, string> = {
  TAG: "o assunto (tag)",
  ENTITY: "a entidade",
};

export const CONFLICT_WINNER_TONE: Record<string, BadgeTone> = {
  TAG: "accent",
  ENTITY: "ok",
};

/**
 * Where each verdict is written — and they are different places deliberately.
 *
 * Entity wins: the tag's name is banned from the subject axis (``DomainStopwords``, scope ``TAG``).
 * Tag wins: the term is recorded as a NER exclusion carrying the tag that justifies it. A screen
 * that did not say this would make the two look like the same write.
 */
export const CONFLICT_WINNER_HINT: Record<string, string> = {
  ENTITY:
    "A grafia é um nome próprio. O nome da tag é banido do eixo de assunto, e a classificação daquela tag se perde.",
  TAG:
    "A grafia é assunto. O termo entra nas exclusões de NER com a tag que o justifica, e o extrator para de devolvê-lo como nome próprio.",
};

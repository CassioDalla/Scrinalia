/**
 * Portuguese labels for the named-entity codes.
 *
 * Only text lives here: the codes (``PER``/``ORG``/``LOC``, ``JUDGE``/``HUMAN``, ``TAG``/``ENTITY``)
 * are the contract's, and the entity types the screens iterate come from the API's own enum.
 */

import { activeMessages } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";
import type { BadgeTone } from "@/lib/hierarchy";

type Entities = Messages["entities"];
type Section = keyof Entities;

function entityField(section: Section, field: "label" | "hint"): Record<string, string> {
  return new Proxy({} as Record<string, string>, {
    get(_target, key) {
      const entry = (activeMessages().entities[section] as Record<string, { label: string; hint: string }>)[
        String(key)
      ];
      return entry?.[field] ?? (field === "label" ? String(key) : "");
    },
  });
}

export const ENTITY_TYPE_LABEL = entityField("type", "label");

export const ENTITY_TYPE_TONE: Record<string, BadgeTone> = {
  PER: "accent",
  ORG: "ok",
  LOC: "warn",
};

export const ENTITY_TYPE_HINT = entityField("type", "hint");

/**
 * Who wrote the link between an entity and a description, which the contract calls its *origin*.
 *
 * The three values are the API's own (``ArchiveEntityOrigin``); only the text lives here. ``UNKNOWN``
 * is not ``AI``: it is the link written before the column existed, and the screen says "não rastreada"
 * instead of crediting the extractor with a row nobody can attribute (#135).
 */
export const ENTITY_ORIGIN_LABEL = entityField("origin", "label");

export const ENTITY_ORIGIN_TONE: Record<string, BadgeTone> = {
  HUMAN: "ok",
  AI: "neutral",
  UNKNOWN: "warn",
};

export const ENTITY_ORIGIN_HINT = entityField("origin", "hint");

/**
 * The warnings the entity merge preview carries — **warnings, not blocks**.
 *
 * The codes are the contract's (``domain/entity_merge.py``); only the text lives here. ``MIXED_TYPES``
 * and ``ORPHAN_MEMBER`` are specific to this axis: a person's name absorbed into an organisation
 * starts resolving as an organisation, and an orphan is exactly the class of row the purge targets.
 */
export const ENTITY_MERGE_FLAG_LABEL = entityField("mergeFlag", "label");

export const ENTITY_MERGE_FLAG_HINT = entityField("mergeFlag", "hint");

/** Who recorded a NER veto: the conflict judge, or an archivist. */
export const EXCLUSION_SOURCE_LABEL = entityField("exclusionSource", "label");

/**
 * The two directions of the bidirectional governance.
 *
 * This is the detail the screen exists to make visible: a veto written here is a *curation
 * decision*, and it is stored apart from the subject-axis stopwords on purpose. Collapsing the two
 * would let a NER veto reach the subject purge, which deletes tags.
 */
export const EXCLUSION_SOURCE_HINT = entityField("exclusionSource", "hint");

export const CONFLICT_WINNER_LABEL = entityField("conflictWinner", "label");

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
export const CONFLICT_WINNER_HINT = entityField("conflictWinner", "hint");

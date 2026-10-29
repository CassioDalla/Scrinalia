/**
 * Portuguese labels for the tag-catalog codes.
 *
 * The codes themselves are the contract's (``MERGE_REASONS``, ``REVIEW_*``); only the text lives
 * here, like everywhere else in the front (see AGENTS.md: code is English, end-user-visible text is
 * Portuguese).
 */

import type { AccessPointPreviewItem } from "@/api/client";
import { fieldMap, stringMap } from "@/i18n/maps";
import type { BadgeTone } from "@/lib/hierarchy";

export const MERGE_REASON_LABEL = stringMap((m) => m.taxonomy.mergeReason);

export const MERGE_REASON_TONE: Record<string, BadgeTone> = {
  TRIGRAM: "neutral",
  PLURAL: "accent",
  MIXED: "warn",
};

/**
 * The review flags are **warnings, not blocks** — the screen must not turn them into a refusal.
 *
 * The collection settled that: 58 agrupamentos carry ``MEMBER_WITH_DIGITS`` and both directions are real
 * (``br-116 ← br 116`` is right, ``rua ← rua 7`` is wrong). The archivist decides; the flag only says
 * where to look.
 */
export const REVIEW_FLAG_LABEL = fieldMap((m) => m.taxonomy.reviewFlag, "label");

export const REVIEW_FLAG_HINT = fieldMap((m) => m.taxonomy.reviewFlag, "hint");

export const PROPOSAL_STATUS_LABEL = stringMap((m) => m.taxonomy.proposalStatus);

export const PROPOSAL_STATUS_TONE: Record<string, BadgeTone> = {
  SUGGESTED: "warn",
  APPROVED: "ok",
  REJECTED: "danger",
  APPLIED: "neutral",
};

export function labelOf(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

/**
 * The axis a banned term was taken out of.
 *
 * The distinction is not cosmetic and the screen has to say it: ``TAG`` (and ``ALL``) feed the
 * subject purge, which **deletes** the matching tags, while ``ENTITY`` only keeps the term out of
 * the NER extraction and never touches a tag. Reading an entity ban in the purge would delete a tag
 * the curator deliberately kept.
 */
export const STOPWORD_SCOPE_LABEL = fieldMap((m) => m.taxonomy.stopwordScope, "label");

export const STOPWORD_SCOPE_HINT = fieldMap((m) => m.taxonomy.stopwordScope, "hint");

/**
 * How a ban on the extraction axis matches an extracted name (#160).
 *
 * Only ``TOKEN`` has to swallow the merged span the engine returns around a noise word
 * (``IPTU do Exemplo``); ``EXACT`` is what a generic word that also starts proper names needs
 * (``alameda`` alone, never ``Alameda Cabral``). The labels are the two behaviours, not the codes.
 */
export const STOPWORD_MATCH_LABEL = fieldMap((m) => m.taxonomy.stopwordMatch, "label");

export const STOPWORD_MATCH_HINT = fieldMap((m) => m.taxonomy.stopwordMatch, "hint");

/**
 * Who planted a ban.
 *
 * The column exists because the purge preview has to tell a term banned **with the archive in mind**
 * from one typed by hand: ``CONFLICT`` came from settling a tag × entity collision and ``EXCLUSION``
 * from declaring the term not-a-subject — both are consequences of another decision — while
 * ``HUMAN`` is an act taken on the blocked-spellings screen.
 */
export const STOPWORD_SOURCE_LABEL = fieldMap((m) => m.taxonomy.stopwordSource, "label");

export const STOPWORD_SOURCE_HINT = fieldMap((m) => m.taxonomy.stopwordSource, "hint");

/**
 * The state of a tag's subject decision, as the archivist reads it.
 *
 * The three states are a partition of the tags with no category (see
 * ``repository/subject_queue.py``), and the labels say which question each one answers. ``ALL`` is
 * not a state: it is the absence of a filter. A producer, a place or a person is **not** a fourth
 * state: the entity axis carries what it is, and the tag × entity conflict screen settles a spelling
 * that is both (ADR 0013).
 */
export const CATALOG_STATE_LABEL = fieldMap((m) => m.taxonomy.catalogState, "label");

export const CATALOG_STATE_HINT = fieldMap((m) => m.taxonomy.catalogState, "hint");

/**
 * The four groups the creation form's access-point summary reads.
 *
 * The server answers one status per entry; the summary only has something to say about the
 * spellings the transfer will create, the ones it will drop, the ones it will map to a synonym, and
 * an existing tag whose stored spelling differs from what was typed. An exact existing tag is the
 * common case and produces no line at all.
 */
export type AccessPointPreviewGroups = {
  created: AccessPointPreviewItem[];
  dropped: AccessPointPreviewItem[];
  synonyms: AccessPointPreviewItem[];
  respelled: AccessPointPreviewItem[];
};

export function groupAccessPointPreview(items: AccessPointPreviewItem[]): AccessPointPreviewGroups {
  return {
    created: items.filter((item) => item.status === "NEW"),
    dropped: items.filter(
      (item) => item.status === "STOPWORD" || item.status === "TOO_SHORT" || item.status === "TOO_LONG",
    ),
    synonyms: items.filter((item) => item.status === "SYNONYM"),
    respelled: items.filter((item) => item.status === "EXISTING" && item.name !== null && item.name !== item.input),
  };
}


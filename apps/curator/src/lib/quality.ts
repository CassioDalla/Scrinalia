/**
 * Portuguese labels for the input-quality codes (Fase 3.5).
 *
 * The two vocabularies here are the ones whose difference is a decision, not a wording:
 * ``rule_kind`` separates cleaning from destroying, and the excerpt ``scope`` says which consumer
 * stops reading a repeated block. Embedding either as a bare string in a screen would hide that.
 */

import { fieldMap, stringMap } from "@/i18n/maps";
import type { BadgeTone } from "@/lib/hierarchy";

export const RULE_KIND_LABEL = fieldMap((m) => m.quality.ruleKind, "label");

export const RULE_KIND_TONE: Record<string, BadgeTone> = {
  REWRITE: "warn",
  VALIDATE: "neutral",
  LLM_CHECK: "accent",
};

export const RULE_KIND_HINT = fieldMap((m) => m.quality.ruleKind, "hint");

export const TARGET_COLUMN_LABEL = stringMap((m) => m.quality.targetColumn);

export const TEMPLATE_STATUS_LABEL = stringMap((m) => m.quality.templateStatus);

export const TEMPLATE_STATUS_TONE: Record<string, BadgeTone> = {
  SUGGESTED: "warn",
  APPROVED: "ok",
  REJECTED: "danger",
};

export const TEMPLATE_ACTION_LABEL = stringMap((m) => m.quality.templateAction);

export const TEMPLATE_SCOPE_LABEL = fieldMap((m) => m.quality.templateScope, "label");

/**
 * ``scope`` is the decision that matters, and the measurement is why.
 *
 * Approving everything the machine suggested **worsened** the ranking (Hit@10 0.562 → 0.500): the
 * title prefix helped the derived title and hurt the vector. So a block is dropped from the
 * consumers it damages and kept where it helps, one scope at a time.
 */
export const TEMPLATE_SCOPE_HINT = fieldMap((m) => m.quality.templateScope, "hint");

export function labelOf(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

/**
 * The reason codes the quality validator writes, in the archivist's language.
 *
 * The column mixes a stable code with an optional payload, and the facet bucket follows that: the
 * bare code for most reasons, and ``RULE_MATCH:<rule>`` for the one whose payload is a catalogue
 * entry. ``LLM_SUSPECT`` carries free text the model wrote about a single title, so its bucket is
 * the code — a sidebar over prose would be a long tail of options that never repeat.
 */
export const ANOMALY_REASON_LABEL = fieldMap((m) => m.quality.anomalyReason, "label");

export const ANOMALY_REASON_HINT = fieldMap((m) => m.quality.anomalyReason, "hint");

/**
 * The bucket key as the archivist reads it.
 *
 * ``RULE_MATCH:data fora do intervalo`` becomes "regra do arquivista: data fora do intervalo", and
 * the key itself is what the filter sends back — the facet's key and the query's value are the same
 * string by construction, on both sides.
 */
export function anomalyReasonLabel(key: string): string {
  const [code = key, ...rest] = key.split(":");
  const base = ANOMALY_REASON_LABEL[code] ?? code;
  return rest.length > 0 ? `${base}: ${rest.join(":")}` : base;
}

/** The code without its payload, for looking up the hint of a bucket key. */
export function anomalyReasonCode(key: string): string {
  return key.split(":")[0] ?? key;
}

/**
 * The shapes the deterministic guard recognises, and what each one means.
 *
 * These are the reason a term never reaches the subject classifier. The guard has been applying them
 * silently inside the worker; the catalogue now says which shape fired, because "não é assunto" with
 * no reason is indistinguishable from a mistake.
 */
export const SIGNAL_LABEL = fieldMap((m) => m.quality.signal, "label");

export const SIGNAL_HINT = fieldMap((m) => m.quality.signal, "hint");

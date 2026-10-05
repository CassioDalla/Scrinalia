/**
 * Portuguese labels for the tag-catalog codes.
 *
 * The codes themselves are the contract's (``MERGE_REASONS``, ``REVIEW_*``); only the text lives
 * here, like everywhere else in the front (see AGENTS.md: code is English, end-user-visible text is
 * Portuguese).
 */

import type { BadgeTone } from "@/lib/hierarchy";

export const MERGE_REASON_LABEL: Record<string, string> = {
  TRIGRAM: "grafia parecida",
  PLURAL: "singular/plural",
  MIXED: "grafia e plural",
};

export const MERGE_REASON_TONE: Record<string, BadgeTone> = {
  TRIGRAM: "neutral",
  PLURAL: "accent",
  MIXED: "warn",
};

/**
 * The review flags are **warnings, not blocks** — the screen must not turn them into a refusal.
 *
 * The collection settled that: 58 clusters carry ``MEMBER_WITH_DIGITS`` and both directions are real
 * (``br-116 ← br 116`` is right, ``rua ← rua 7`` is wrong). The archivist decides; the flag only says
 * where to look.
 */
export const REVIEW_FLAG_LABEL: Record<string, string> = {
  MEMBER_WITH_DIGITS: "membro com número",
  WEAK_MEMBER: "membro fraco",
  CATEGORY_WOULD_BE_LOST: "gaveta seria perdida",
  MEMBER_IS_SYNONYM: "membro é grafia absorvida",
};

export const REVIEW_FLAG_HINT: Record<string, string> = {
  MEMBER_WITH_DIGITS:
    "Algum membro tem número no nome. Pode ser a mesma coisa (br-116 / br 116) ou outra (rua / rua 7): o número não decide.",
  WEAK_MEMBER:
    "A similaridade de algum membro com a canônica é baixa; o cluster pode estar juntando coisas diferentes.",
  CATEGORY_WOULD_BE_LOST:
    "Um dos membros está numa gaveta de assunto que a canônica não tem. Unificar apaga essa classificação.",
  MEMBER_IS_SYNONYM:
    "Algum membro é uma grafia que já foi absorvida por um merge anterior — o cluster pode ser reflexo de uma decisão antiga.",
};

export const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  SUGGESTED: "sugerida",
  APPROVED: "aprovada",
  REJECTED: "rejeitada",
};

export const PROPOSAL_STATUS_TONE: Record<string, BadgeTone> = {
  SUGGESTED: "warn",
  APPROVED: "ok",
  REJECTED: "danger",
};

export function labelOf(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

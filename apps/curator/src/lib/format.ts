import type { ArchiveReviewStatus } from "@/api/client";

const dateFormatter = new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" });
const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
const numberFormatter = new Intl.NumberFormat("pt-BR");

export function formatDate(value?: string | null): string {
  if (!value) return "sem data";
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateTimeFormatter.format(parsed);
}

export function formatCount(value: number): string {
  return numberFormatter.format(value);
}

/**
 * Human labels for the review states.
 *
 * The API speaks the enum; the archivist reads Portuguese. Keeping the mapping here and not in the
 * database is what lets the contract stay in English (see AGENTS.md).
 */
export const REVIEW_STATUS_LABEL: Record<ArchiveReviewStatus, string> = {
  PENDING_AI: "Aguardando IA",
  AI_APPROVED: "Aprovado pela IA",
  NEEDS_REVIEW: "Precisa de revisão",
  HUMAN_APPROVED: "Revisado por humano",
  REJECTED: "Rejeitado",
};

export const REVIEW_STATUS_TONE: Record<ArchiveReviewStatus, "neutral" | "ok" | "warn" | "danger"> = {
  PENDING_AI: "neutral",
  AI_APPROVED: "ok",
  NEEDS_REVIEW: "warn",
  HUMAN_APPROVED: "ok",
  REJECTED: "danger",
};

/** The badge rule of the sitemap: the winning drawer plus how many others the document carries. */
export function subjectBadge(
  macroCategories: { name: string; tag_count: number }[],
  activeCategoryName?: string,
): { name: string; others: number } | null {
  if (macroCategories.length === 0) return null;

  // With a subject filter active, that category is promoted regardless of the vote: it is what
  // gives the archivist confidence that the result really is about what they searched for.
  const active = activeCategoryName
    ? macroCategories.find((category) => category.name === activeCategoryName)
    : undefined;
  const winner = active ?? macroCategories.reduce((best, current) =>
    current.tag_count > best.tag_count ? current : best,
  );
  const others = macroCategories.filter((category) => category.name !== winner.name).length;

  return { name: winner.name, others };
}

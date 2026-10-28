import type { ArchiveReviewStatus } from "@/api/client";
import { activeLocale, activeMessages, type Locale } from "@/i18n/locale";

/**
 * One formatter set per locale, built once.
 *
 * `Intl` constructors are not free and these functions are called 220 times across the screens, so
 * the set is cached by locale instead of rebuilt on every render.
 */
type Formatters = {
  date: Intl.DateTimeFormat;
  dateTime: Intl.DateTimeFormat;
  number: Intl.NumberFormat;
  plural: Intl.PluralRules;
};

const FORMATTERS = new Map<Locale, Formatters>();

function formattersFor(locale: Locale): Formatters {
  const cached = FORMATTERS.get(locale);
  if (cached) return cached;

  const built: Formatters = {
    date: new Intl.DateTimeFormat(locale, { dateStyle: "medium" }),
    dateTime: new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }),
    number: new Intl.NumberFormat(locale),
    plural: new Intl.PluralRules(locale),
  };
  FORMATTERS.set(locale, built);
  return built;
}

function current(): Formatters {
  return formattersFor(activeLocale());
}

export function formatDate(value?: string | null): string {
  if (!value) return activeMessages().format.noDate;
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : current().date.format(parsed);
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : current().dateTime.format(parsed);
}

export function formatCount(value: number): string {
  return current().number.format(value);
}

/**
 * "1 descrição" / "2 descrições" — and "1 description" / "2 descriptions".
 *
 * A count of one is common here (a rung with a single record, a tag carried by one description), and
 * the card that said "1 descrições" was the first thing the level screen showed. The plural category
 * comes from `Intl.PluralRules`; the two forms come from the catalogue.
 */
export function descricoes(value: number): string {
  const forms = activeMessages().format.descriptions;
  const form = current().plural.select(value) === "one" ? forms.one : forms.other;
  return `${formatCount(value)} ${form}`;
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
  HUMAN_APPROVED: "Revisado por pessoa",
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

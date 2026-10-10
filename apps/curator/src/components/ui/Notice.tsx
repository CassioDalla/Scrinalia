import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * The one inline notice: a paragraph that states something the data does not.
 *
 * Every screen here has one, and they were the loudest thing the interface disagreed with itself
 * about: thirty-four of them, hand-copied, in **sixteen** class combinations. The same warning was
 * `ring-(--color-warn)/20` on one screen and `/25` on the next; the same panel was `px-3 py-2` here
 * and `px-2 py-1.5` there; and one of them — the tags screen — named `--color-surface-2`, a token
 * `styles.css` never defines, so the browser dropped the declaration and the box rendered with no
 * background at all. A gate cannot see any of that in a `<p>`; it can see it in one component.
 *
 * The five tones are the palette's, and each one is a meaning the screens already use: `warn` for a
 * consequence the archivist has to read before writing, `danger` for the irreversible, `ok` for what
 * a run just did, `accent` for how the catalogue works, `neutral` for a plain aside. The text is
 * `text-xs` throughout — a notice is a footnote, never the page.
 */
export type NoticeTone = "neutral" | "accent" | "warn" | "danger" | "ok";

const TONES: Record<NoticeTone, string> = {
  neutral: "bg-black/[0.02] text-(--color-ink) ring-(--color-line)",
  accent: "bg-(--color-accent)/5 text-(--color-accent) ring-(--color-accent)/20",
  warn: "bg-(--color-warn)/5 text-(--color-warn) ring-(--color-warn)/20",
  danger: "bg-(--color-danger)/5 text-(--color-danger) ring-(--color-danger)/20",
  ok: "bg-(--color-ok)/5 text-(--color-ok) ring-(--color-ok)/20",
};

export function Notice({
  tone = "neutral",
  as: Tag = "p",
  children,
  className,
}: {
  tone?: NoticeTone;
  /**
   * `div` for the notices whose body is a block — a `grid` of rows, a list of what a purge would
   * reach. A `<div>` inside a `<p>` is invalid HTML that the browser silently reparents, so the
   * element has to be the caller's choice and not a default the component hides.
   */
  as?: "p" | "div";
  children: ReactNode;
  /** For the two shapes that are not a single line: a `grid` of rows, a `p-3` block. */
  className?: string;
}) {
  return <Tag className={cn("rounded-md px-3 py-2 text-xs ring-1 ring-inset", TONES[tone], className)}>{children}</Tag>;
}

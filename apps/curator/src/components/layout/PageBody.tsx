import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * The column a screen's content lives in, under the header.
 *
 * Every route had its own version of this line and they had drifted: `max-w-5xl` on most,
 * `max-w-4xl` on five, `max-w-6xl` on one, and none at all on two — so the width of the collection
 * changed depending on which screen you were standing on, and a wide monitor showed two screens
 * that stopped growing at different points.
 *
 * There is **no maximum width**: the column fills whatever the window gives it. A cap is a decision
 * about one screen's content, and it belongs to that content — a paragraph keeps its own measure
 * (`max-w-prose`, `max-w-3xl`) because a 200-character line is unreadable, and a form keeps its own
 * (`max-w-md`) because a text field as wide as the window is worse than a narrow one. What is gone
 * is the cap on the *screen*, which was never a decision: it was drift.
 *
 * `className` is for the layouts that are not a stacked column — the collection's facet sidebar and
 * the arrangement diagnostic's two panes are `flex` — and `cn`/`tailwind-merge` is what lets them
 * replace the default instead of sitting beside it.
 */
export function PageBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid gap-4 px-6 py-5", className)}>{children}</div>;
}

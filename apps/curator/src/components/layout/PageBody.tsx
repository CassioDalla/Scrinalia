import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * The column a screen's content lives in, under the header.
 *
 * Every route had its own version of this line and they had drifted: `max-w-5xl` on most,
 * `max-w-4xl` on five, `max-w-6xl` on one, and none at all on two — so the reading width of the
 * collection changed depending on which screen you were standing on. The default is the width the
 * majority used.
 *
 * `className` is not an escape hatch for spacing: it is for the two layouts that are not a stacked
 * column — the collection's facet sidebar and the arrangement diagnostic's two panes are `flex`, and
 * they pass their own display and width. `cn`/`tailwind-merge` is what makes the override work: the
 * caller's `max-w-4xl` replaces the default instead of sitting beside it.
 */
export function PageBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid max-w-5xl gap-4 px-6 py-5", className)}>{children}</div>;
}

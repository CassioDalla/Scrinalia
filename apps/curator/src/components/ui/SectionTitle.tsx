import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * A heading inside a screen: "Ativas", "Aposentadas", "Vocabulário de arranjo".
 *
 * The screens that split a list in two — the drawers, the collection vocabulary — each wrote their
 * own `<h2>` with its own class string, so the same rank of heading was spelled differently on each
 * one. One component, one size.
 *
 * It is deliberately **not** every `<h2>` in the app: the two panel headings that sit inside a side
 * pane (the tree's branch title, the diagnostic's issue name) are a rank of their own and carry a
 * `text-base`, so they keep their own element rather than passing a `className` that would undo this
 * one. A primitive that is overridden everywhere is a primitive that is not defining anything.
 */
export function SectionTitle({ children, className }: { children: ReactNode; className?: string }) {
  return <h2 className={cn("text-sm font-semibold", className)}>{children}</h2>;
}

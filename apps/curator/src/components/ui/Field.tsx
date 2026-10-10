import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * The one labelled form field.
 *
 * Sixty labels in this UI were the same three lines copied out — `flex flex-col gap-1 text-xs`, a
 * muted `<span>` with the name, the input — and nine more used `grid gap-1` instead, which stacks
 * the same way and reads as a different component to whoever edits it next. The gap between the
 * label and its control was the one thing a screen could get wrong without anybody noticing, and
 * several did: `gap-2`, `pb-3`, a bare text node instead of the span.
 *
 * The label is a `ReactNode` because a few of them carry `<code>` — the field that asks the
 * archivist to type a reference code has to show that code in the label. `hint` is for the
 * explanation that belongs under the control rather than beside it.
 */
export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-1 text-xs", className)}>
      <span className="text-(--color-muted)">{label}</span>
      {children}
      {hint ? <span className="text-(--color-muted)">{hint}</span> : null}
    </label>
  );
}

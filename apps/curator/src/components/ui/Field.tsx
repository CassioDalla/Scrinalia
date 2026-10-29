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
 *
 * `info` is the discreet slot: it renders **outside** the `<label>`, because the `<button>` of a
 * `Hint` inside a label is invalid HTML and pollutes the input's accessible name with the trigger's
 * own label. `hint` stays visible; this slot never replaces it, it only carries what is secondary.
 *
 * `htmlFor` is for a **composite** control, whose chips carry their own remove buttons: a `<button>`
 * inside a `<label>` is invalid HTML and clicking it would also activate the label. In that mode the
 * label is a sibling pointing at the control's input by id, and `hintId` names the visible hint so
 * the control can include it in `aria-describedby`. With no `htmlFor` the label still wraps the
 * control, which is what every simple field wants.
 */
export function Field({
  label,
  hint,
  info,
  children,
  className,
  htmlFor,
  hintId,
}: {
  label: ReactNode;
  hint?: ReactNode;
  info?: ReactNode;
  children: ReactNode;
  className?: string;
  htmlFor?: string;
  hintId?: string;
}) {
  const hintNode = hint ? (
    <span id={hintId} className="text-(--color-muted)">
      {hint}
    </span>
  ) : null;

  if (htmlFor) {
    return (
      <div className={cn("flex items-start gap-1", className)}>
        <div className="flex min-w-0 flex-1 flex-col gap-1 text-xs">
          <label htmlFor={htmlFor} className="text-(--color-muted)">
            {label}
          </label>
          {children}
          {hintNode}
        </div>
        {info ? <span className="shrink-0">{info}</span> : null}
      </div>
    );
  }

  return (
    <div className={cn("flex items-start gap-1", className)}>
      <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs">
        <span className="text-(--color-muted)">{label}</span>
        {children}
        {hintNode}
      </label>
      {info ? <span className="shrink-0">{info}</span> : null}
    </div>
  );
}

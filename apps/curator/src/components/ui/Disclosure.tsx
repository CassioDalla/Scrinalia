import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

/**
 * A card whose decision body is revealed on demand.
 *
 * The screens that edit a catalogue — the arrangement rungs, the ladder of levels, the subject
 * drawers — render one card per row and put the whole edit form inside each one. At five rows that
 * reads as a list; at fifty it reads as a wall, and the archivist cannot see the catalogue for the
 * forms. Collapsing is what makes the list scannable again: the row keeps the evidence it needs to be
 * judged, and the form appears only for the row being decided.
 *
 * ``header`` is deliberately **inside** the toggle and ``actions`` outside it: a header may hold text
 * and badges but never a control, because a button nested in a button is invalid HTML and a click
 * that means two things at once. What must remain clickable on a collapsed row (retire a drawer,
 * deactivate a rung) goes in ``actions``, which sits outside the toggle.
 */
export function Disclosure({
  header,
  children,
  actions,
  triggerLabel,
  triggerCloseLabel = "fechar",
  defaultOpen = false,
  open,
  onOpenChange,
  className,
  bodyClassName,
  /** Tells the archivist what the chevron does; the row itself says "decidir" in most screens. */
  toggleLabel = "Expandir",
}: {
  header: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  /**
   * An explicit button, for the cards whose whole job is "add one more".
   *
   * A chevron is a weak affordance for a write the archivist came to the screen looking for: the
   * report that "não estou achando o botão" was about an action that existed and had no button. On a
   * row of the catalogue the chevron is enough — the row *is* the object — but the create card gets
   * a labelled button of its own.
   */
  triggerLabel?: string;
  triggerCloseLabel?: string;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  bodyClassName?: string;
  toggleLabel?: string;
}) {
  const [internal, setInternal] = useState(defaultOpen);
  const isOpen = open ?? internal;

  const toggle = () => {
    const next = !isOpen;
    setInternal(next);
    onOpenChange?.(next);
  };

  return (
    <Card className={className}>
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={isOpen}
          title={isOpen ? "Recolher" : toggleLabel}
          className="flex min-w-0 flex-1 items-start gap-2 rounded text-left"
        >
          <span
            aria-hidden
            className="mt-0.5 grid size-5 shrink-0 place-items-center rounded text-xs text-(--color-muted)"
          >
            {isOpen ? "▾" : "▸"}
          </span>
          <span className="min-w-0 flex-1">{header}</span>
        </button>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {triggerLabel ? (
            <Button size="sm" variant="primary" onClick={toggle} aria-expanded={isOpen} className="w-36 text-center">
              {isOpen ? triggerCloseLabel : triggerLabel}
            </Button>
          ) : null}
          {actions}
        </div>
      </div>
      {isOpen ? <div className={cn("border-t border-(--color-line) px-4 py-3", bodyClassName)}>{children}</div> : null}
    </Card>
  );
}

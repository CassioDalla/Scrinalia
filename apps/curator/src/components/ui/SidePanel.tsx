import { useEffect, useRef, type ReactNode } from "react";

/**
 * One item in detail, over the list that produced it, without leaving the screen.
 *
 * Deliberately **not** called `Drawer`. `drawer` is already this codebase's word for a subject
 * category — the API's own field docstring says "Drawer to move the tag into" and the Portuguese
 * copy calls it *Categoria* — so a `Drawer` component would put two meanings of the same word in
 * the same package, and every call site would read wrong.
 *
 * It is a dialog and declares itself one, which is a promise about the keyboard: Escape closes it,
 * the backdrop closes it, Tab cycles inside it while it is open, and focus returns to whatever had
 * it when the panel opened. A read-only preview that let Tab walk out into the list behind it
 * would be a modal in name only, and the `aria-modal` would be a lie.
 */
export function SidePanel({
  label,
  onClose,
  children,
  footer,
}: {
  /** The accessible name of the dialog; the visible heading is `children`' business. */
  label: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Focus moves in on open and back to the row that opened it on close, so Escape is not the only
    // way back to the keyboard: without the restore, focus would fall to the document body and the
    // next Tab would start from the top of the page.
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const target = panel.current?.querySelector<HTMLElement>("[data-autofocus]") ?? panel.current;
    target?.focus();
    return () => previous?.focus();
  }, []);

  useEffect(() => {
    const focusable = () =>
      Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* The backdrop is the pointer's dismissal, and it is not in the tab order: Escape is. */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-(--color-surface) shadow-xl ring-1 ring-(--color-line)"
      >
        <div className="flex-1 px-4 py-4">{children}</div>
        {footer ? <div className="border-t border-(--color-line) px-4 py-3">{footer}</div> : null}
      </div>
    </div>
  );
}

/**
 * The dismiss control every panel carries, so the gesture is one component and not one per screen.
 *
 * It is the panel's autofocus target: the first thing a keyboard gets is the way out.
 */
export function SidePanelClose({ onClose, label = "Fechar" }: { onClose: () => void; label?: string }) {
  return (
    <button
      type="button"
      data-autofocus
      onClick={onClose}
      className="rounded px-2 py-1 text-xs text-(--color-muted) hover:text-(--color-ink)"
    >
      {label} ✕
    </button>
  );
}

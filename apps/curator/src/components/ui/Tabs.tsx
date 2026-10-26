import { useId } from "react";

import { cn } from "@/lib/cn";

export type TabItem = {
  id: string;
  label: string;
  /**
   * A secondary explanation of what the view answers.
   *
   * It rides on the native ``title`` while the shared ``Hint`` does not exist (#208): hover-only
   * for a mouse, which is the same gap that issue exists to close. The visually hidden twin is what
   * keeps the text reachable by a screen reader in the meantime; both go together when the hint
   * lands. It is never the only description of something the archivist must know in order to act.
   */
  hint?: string;
};

/**
 * Tabs whose state lives in the URL.
 *
 * The dossier has four sub-screens, and the archivist shares links to them ("look at the subjects
 * of this one"), so the active tab cannot be component state.
 */
export function Tabs({
  items,
  active,
  onChange,
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
}) {
  const hintBase = useId();

  return (
    <>
      <div role="tablist" className="flex gap-1 border-b border-(--color-line)">
        {items.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={item.id === active}
            aria-describedby={item.hint ? `${hintBase}-${item.id}` : undefined}
            title={item.hint}
            onClick={() => onChange(item.id)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition",
              item.id === active
                ? "border-(--color-accent) text-(--color-ink)"
                : "border-transparent text-(--color-muted) hover:text-(--color-ink)",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {/* Outside the tablist: a description is text, not a tab. */}
      {items.map((item) =>
        item.hint ? (
          <span key={item.id} id={`${hintBase}-${item.id}`} className="sr-only">
            {item.hint}
          </span>
        ) : null,
      )}
    </>
  );
}

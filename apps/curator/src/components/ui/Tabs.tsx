import { Fragment } from "react";

import { Hint } from "@/components/ui/Hint";
import { cn } from "@/lib/cn";

export type TabItem = {
  id: string;
  label: string;
  /**
   * A secondary explanation of what the view answers.
   *
   * A tab is already a `<button>`, so it becomes the `Hint` trigger itself (`asChild`) instead of
   * nesting a second button. The text is in the tooltip and described by the tab, which keeps it
   * reachable by mouse, keyboard and touch. It is never the only description of something the
   * archivist must know in order to act.
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
  return (
    <div role="tablist" className="flex gap-1 border-b border-(--color-line)">
      {items.map((item) => {
        const trigger = (
          <button
            role="tab"
            aria-selected={item.id === active}
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
        );

        return item.hint ? (
          <Hint key={item.id} asChild text={item.hint} align="start" placement="bottom">
            {trigger}
          </Hint>
        ) : (
          <Fragment key={item.id}>{trigger}</Fragment>
        );
      })}
    </div>
  );
}

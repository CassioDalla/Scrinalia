import { cn } from "@/lib/cn";

export type TabItem = { id: string; label: string };

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
      {items.map((item) => (
        <button
          key={item.id}
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
      ))}
    </div>
  );
}

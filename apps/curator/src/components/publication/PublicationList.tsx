import type { ReactNode } from "react";

import type { PublicationItem } from "@/api/client";
import { Badge } from "@/components/ui/Badge";
import { useCopy } from "@/i18n/context";
import { formatDate } from "@/lib/format";

/**
 * One of the page's two lists: the approved without a channel, or what the channels carry.
 *
 * The same table serves both because the row is the same description; what changes is the action
 * column and whether a checkbox is offered. The channels are badges, not a sentence, so a record on
 * two channels reads at a glance.
 */
export function PublicationList({
  items,
  selected,
  onToggle,
  onToggleAll,
  renderAction,
}: {
  items: PublicationItem[];
  selected?: ReadonlySet<string>;
  onToggle?: (descriptionId: string) => void;
  onToggleAll?: () => void;
  renderAction?: (item: PublicationItem) => ReactNode;
}) {
  const messages = useCopy();
  const columns = messages.pages.publication.columns;
  const selectable = selected !== undefined && onToggle !== undefined;
  const allSelected = items.length > 0 && items.every((item) => selected?.has(item.description_id));

  return (
    <div className="overflow-x-auto rounded-lg ring-1 ring-(--color-line)">
      <table className="w-full text-left text-sm">
        <thead className="bg-black/[0.02] text-xs text-(--color-muted)">
          <tr>
            {selectable ? (
              <th className="w-8 px-3 py-2">
                <input
                  type="checkbox"
                  aria-label={messages.pages.publication.toPublish.selectAll}
                  checked={allSelected}
                  onChange={onToggleAll}
                />
              </th>
            ) : null}
            <th className="px-3 py-2 font-medium">{columns.title}</th>
            <th className="px-3 py-2 font-medium">{columns.level}</th>
            <th className="px-3 py-2 font-medium">{columns.date}</th>
            {selectable ? null : <th className="px-3 py-2 font-medium">{columns.channels}</th>}
            {renderAction ? <th className="px-3 py-2 text-right font-medium">{columns.actions}</th> : null}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.description_id} className="border-t border-(--color-line)/60">
              {selectable ? (
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label={item.title}
                    checked={selected?.has(item.description_id) ?? false}
                    onChange={() => onToggle?.(item.description_id)}
                  />
                </td>
              ) : null}
              <td className="max-w-0 px-3 py-2">
                <span className="block truncate" title={item.title}>
                  {item.title}
                </span>
                <span className="block truncate text-[10px] text-(--color-muted)">{item.description_id}</span>
              </td>
              <td className="px-3 py-2 text-xs text-(--color-muted)">{item.level ?? "—"}</td>
              <td className="px-3 py-2 text-xs text-(--color-muted)">{formatDate(item.document_date)}</td>
              {selectable ? null : (
                <td className="px-3 py-2">
                  <span className="flex flex-wrap gap-1">
                    {(item.channels ?? []).map((code) => (
                      <Badge key={code} tone="accent">
                        {code}
                      </Badge>
                    ))}
                  </span>
                </td>
              )}
              {renderAction ? (
                <td className="px-3 py-2 text-right whitespace-nowrap">{renderAction(item)}</td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

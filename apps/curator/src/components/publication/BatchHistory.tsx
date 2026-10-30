import type { PublicationBatch } from "@/api/client";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { formatCount, formatDateTime } from "@/lib/format";

const ACTION_TONE = {
  PUBLISH: "ok",
  EXCLUDE: "warn",
  REVOKE: "danger",
  UNEXCLUDE: "neutral",
} as const;

/**
 * "Histórico": every publication gesture, newest first, with the undo.
 *
 * The undo is offered only while the batch is open; a batch that was already undone says so with
 * who and when. The API is the authority on both — a second undo is refused there — so the button
 * being hidden is a courtesy, not the rule.
 */
export function BatchHistory({
  batches,
  onUndo,
  pending,
}: {
  batches: PublicationBatch[];
  onUndo: (batchId: number) => void;
  pending: boolean;
}) {
  const messages = useCopy();
  const copy = messages.pages.publication;
  const columns = copy.columns;

  return (
    <div className="overflow-x-auto rounded-lg ring-1 ring-(--color-line)">
      <table className="w-full text-left text-sm">
        <thead className="bg-black/[0.02] text-xs text-(--color-muted)">
          <tr>
            <th className="px-3 py-2 font-medium">{columns.action}</th>
            <th className="px-3 py-2 font-medium">{columns.channels}</th>
            <th className="px-3 py-2 font-medium">{columns.count}</th>
            <th className="px-3 py-2 font-medium">{columns.author}</th>
            <th className="px-3 py-2 font-medium">{columns.state}</th>
            <th className="px-3 py-2 text-right font-medium">{columns.actions}</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((batch) => (
            <tr key={batch.batch_id} className="border-t border-(--color-line)/60">
              <td className="px-3 py-2">
                <Badge tone={ACTION_TONE[batch.action]}>{batch.action}</Badge>
                {batch.note ? (
                  <span className="block text-[11px] text-(--color-muted)">{batch.note}</span>
                ) : null}
              </td>
              <td className="px-3 py-2">
                <span className="flex flex-wrap gap-1">
                  {(batch.channels ?? []).map((code) => (
                    <Badge key={code} tone="neutral">
                      {code}
                    </Badge>
                  ))}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-(--color-muted)">
                <span className="block">{fill(copy.history.applied, { count: formatCount(batch.applied_count) })}</span>
                <span className="block">{fill(copy.history.skipped, { count: formatCount(batch.skipped_count) })}</span>
              </td>
              <td className="px-3 py-2 text-xs text-(--color-muted)">
                <span className="block">{batch.requested_by ?? "—"}</span>
                <span className="block">{formatDateTime(batch.created_at)}</span>
              </td>
              <td className="px-3 py-2 text-xs text-(--color-muted)">
                {batch.undone_at
                  ? fill(copy.history.undone, {
                      date: formatDateTime(batch.undone_at),
                      name: batch.undone_by ?? "—",
                    })
                  : "—"}
              </td>
              <td className="px-3 py-2 text-right">
                {batch.undone_at ? null : (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={pending}
                    onClick={() => onUndo(batch.batch_id)}
                  >
                    {copy.history.undo}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

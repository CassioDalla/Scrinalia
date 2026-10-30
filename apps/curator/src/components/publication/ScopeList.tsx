import type { PublicationScope } from "@/api/client";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { formatCount, formatDateTime } from "@/lib/format";

/**
 * "Publicações por ramo": the positive scopes and the negative ones, per channel.
 *
 * The counts are different facts and are printed as such: for an inclusion, how many descriptions
 * its revoke would take away; for an exclusion, how many approved descriptions the node holds — the
 * number that explains what the exclusion is keeping private.
 */
export function ScopeList({
  scopes,
  onAction,
}: {
  scopes: PublicationScope[];
  onAction: (scope: PublicationScope) => void;
}) {
  const messages = useCopy();
  const copy = messages.pages.publication;
  const columns = copy.columns;

  return (
    <div className="overflow-x-auto rounded-lg ring-1 ring-(--color-line)">
      <table className="w-full text-left text-sm">
        <thead className="bg-black/[0.02] text-xs text-(--color-muted)">
          <tr>
            <th className="px-3 py-2 font-medium">{columns.node}</th>
            <th className="px-3 py-2 font-medium">{columns.channel}</th>
            <th className="px-3 py-2 font-medium">{columns.count}</th>
            <th className="px-3 py-2 font-medium">{columns.author}</th>
            <th className="px-3 py-2 text-right font-medium">{columns.actions}</th>
          </tr>
        </thead>
        <tbody>
          {scopes.map((scope) => (
            <tr key={`${scope.kind}-${scope.scope_id}`} className="border-t border-(--color-line)/60">
              <td className="max-w-0 px-3 py-2">
                <span className="flex items-center gap-2">
                  <Badge tone={scope.kind === "INCLUSION" ? "accent" : "warn"}>
                    {scope.kind === "INCLUSION" ? copy.branches.inclusion : copy.branches.exclusion}
                  </Badge>
                  <span className="truncate" title={scope.node_title ?? scope.node_id}>
                    {scope.node_title ?? scope.node_id}
                  </span>
                </span>
                <span className="block text-[10px] text-(--color-muted)">{scope.node_path}</span>
                {scope.note ? (
                  <span className="block text-[11px] text-(--color-muted)">{scope.note}</span>
                ) : null}
              </td>
              <td className="px-3 py-2 text-xs">
                <Badge tone="neutral">{scope.channel_label}</Badge>
                {scope.include_descendants ? null : (
                  <span className="ml-1 text-[10px] text-(--color-muted)">{copy.branches.directScope}</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs text-(--color-muted)">
                {fill(copy.branches.counts, {
                  covered: formatCount(scope.covered_count),
                  approved: formatCount(scope.approved_count),
                })}
              </td>
              <td className="px-3 py-2 text-xs text-(--color-muted)">
                <span className="block">{scope.created_by ?? "—"}</span>
                <span className="block">{formatDateTime(scope.created_at)}</span>
              </td>
              <td className="px-3 py-2 text-right">
                <Button size="sm" variant="secondary" onClick={() => onAction(scope)}>
                  {scope.kind === "INCLUSION" ? copy.branches.revoke : copy.branches.unexclude}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

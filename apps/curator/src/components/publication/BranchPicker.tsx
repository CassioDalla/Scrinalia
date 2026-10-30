import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { queries } from "@/api/queries";
import { Button } from "@/components/ui/Button";
import { ErrorState, Spinner } from "@/components/ui/Feedback";
import { SidePanel } from "@/components/ui/SidePanel";
import { useCopy } from "@/i18n/context";
import { nodeLabel } from "@/lib/hierarchy";

export type BranchChoice = { id: string; title: string } | null;

/**
 * Chooses one arrangement node to filter — or to publish — the page.
 *
 * The read is lazy like the tree screen's: the roots first, then the subtree of the branch the
 * curator drilled into. Loading the whole forest flat would be truncated by the page limit, and a
 * picker that silently misses half the collection is worse than one that asks for another click.
 */
export function BranchPicker({ onPick, onClose }: { onPick: (choice: BranchChoice) => void; onClose: () => void }) {
  const messages = useCopy();
  const [root, setRoot] = useState<string | null>(null);
  const roots = useQuery(queries.tree(undefined, 0));
  const branch = useQuery({ ...queries.tree(root ?? undefined, 10), enabled: root !== null });
  const nodes = root === null ? (roots.data?.items ?? []) : (branch.data?.items ?? []);
  const loading = root === null ? roots.isPending : branch.isPending;
  const error = root === null ? roots.error : branch.error;
  const total = root === null ? (roots.data?.total ?? 0) : (branch.data?.total ?? 0);

  return (
    <SidePanel
      label={messages.pages.publication.filter.choose}
      onClose={onClose}
      footer={
        <div className="flex flex-wrap justify-between gap-2">
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={root === null ? "primary" : "secondary"}
              onClick={() => setRoot(null)}
            >
              {messages.pages.publication.filter.all}
            </Button>
            {root !== null ? (
              <Button size="sm" variant="ghost" onClick={() => setRoot(null)}>
                {messages.pages.publication.actions.back}
              </Button>
            ) : null}
          </div>
          <Button size="sm" variant="ghost" onClick={() => onPick(null)}>
            {messages.pages.publication.filter.clear}
          </Button>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="text-xs text-(--color-muted)">{messages.pages.publication.filter.branch}</p>
        {loading ? <Spinner label={messages.common.readingDescriptions} /> : null}
        {error ? <ErrorState error={error} /> : null}
        <ul className="max-h-[55vh] overflow-y-auto">
          {nodes.map((node) => (
            <li
              key={node.description_id}
              className="flex items-center gap-2 border-b border-(--color-line)/60 py-1"
            >
              <span
                className="min-w-0 flex-1 truncate text-sm"
                style={{ paddingLeft: `${Math.max(node.path.split(".").length - 1, 0) * 12}px` }}
                title={node.title ?? undefined}
              >
                {nodeLabel(node)}
              </span>
              {(node.children_count ?? 0) > 0 ? (
                <Button size="sm" variant="ghost" onClick={() => setRoot(node.description_id)}>
                  ▸
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onPick({ id: node.description_id, title: nodeLabel(node) })}
              >
                {messages.pages.publication.actions.chooseBranch}
              </Button>
            </li>
          ))}
        </ul>
        {total > nodes.length ? (
          <p className="text-xs text-(--color-muted)">
            {total} {nodes.length}
          </p>
        ) : null}
      </div>
    </SidePanel>
  );
}

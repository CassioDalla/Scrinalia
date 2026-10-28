import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  applyMaterialisation,
  previewMaterialisation,
  undoMaterialisation,
  type MaterialisationPreview,
  type MaterialisationResult,
} from "@/api/client";
import { queries } from "@/api/queries";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDateTime } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";
import { ACTION_LABEL, ACTION_TONE, PLAN_STATUS_LABEL, PLAN_STATUS_TONE, labelOf } from "@/lib/hierarchy";

/**
 * The third step of the plan: materialise the tree the decisions describe.
 *
 * Two rules of the sitemap are enforced here and not by convention:
 *
 * * **the apply does not exist before a preview.** The API computes both with the same planner, so
 *   the numbers cannot diverge — but the archivist still has to see them, and a button that is
 *   simply disabled until a dry run happened is the only version of that rule a screen can keep;
 * * **the write is reversible and the reversal is visible.** Every applied run appears in the
 *   ledger with what it moved, and the undo sits next to it instead of in a documentation page.
 */
export function MaterialisationPanel({
  totalPlans,
  statusCounts,
}: {
  totalPlans: number;
  statusCounts: Record<string, number>;
}) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<MaterialisationPreview | null>(null);
  const [result, setResult] = useState<MaterialisationResult | null>(null);
  const [note, setNote] = useState("");
  const [showAllItems, setShowAllItems] = useState(false);
  const [logLimit, setLogLimit] = useState(10);
  const [logTerm, setLogTerm] = useState("");

  const settledLogTerm = useDebounced(logTerm);
  const term = settledLogTerm.trim();
  const log = useQuery(queries.materialisationLog(logLimit, term.length > 0 ? term : undefined));
  const approved = statusCounts.APPROVED ?? 0;
  const decided = totalPlans - (statusCounts.SUGGESTED ?? 0);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["hierarchy", "plans"] });
    void queryClient.invalidateQueries({ queryKey: ["hierarchy", "materialisation", "log"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    void queryClient.invalidateQueries({ queryKey: ["hierarchy", "diagnostics"] });
  };

  const dryRun = useMutation({
    mutationFn: () => previewMaterialisation({ note: note || null, limit: 500 }),
    onSuccess: (data) => {
      setPreview(data);
      setResult(null);
      setShowAllItems(false);
    },
  });

  const apply = useMutation({
    mutationFn: () => applyMaterialisation({ note: note || null, limit: 500 }),
    onSuccess: (data) => {
      setResult(data);
      setPreview(null);
      invalidate();
    },
  });

  const undo = useMutation({
    mutationFn: (materialisationId: number) => undoMaterialisation(materialisationId),
    onSuccess: () => {
      setResult(null);
      invalidate();
    },
  });

  const items = preview?.items ?? [];
  const visibleItems = showAllItems ? items : items.slice(0, 8);

  return (
    <div className="flex flex-col gap-3">
      <Card>
        <CardHeader>
          <p className="text-sm font-medium">{messages.pages.materialisation.decision}</p>
        </CardHeader>
        <CardBody className="flex flex-col gap-3">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-2xl font-semibold tabular-nums">{formatCount(decided)}</span>
              <span className="text-xs text-(--color-muted)">
                {fill(messages.pages.materialisation.decidedOf, { total: formatCount(totalPlans) })}
              </span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/10">
              <div
                className="h-full rounded-full bg-(--color-accent) transition-all"
                style={{ width: totalPlans > 0 ? `${(decided / totalPlans) * 100}%` : "0%" }}
              />
            </div>
          </div>
          <ul className="flex flex-wrap gap-2">
            {Object.entries(statusCounts).map(([status, count]) => (
              <li key={status}>
                <Badge tone={PLAN_STATUS_TONE[status] ?? "neutral"}>
                  {labelOf(PLAN_STATUS_LABEL, status)}: {formatCount(count)}
                </Badge>
              </li>
            ))}
          </ul>
          <p className="text-xs text-(--color-muted)">{messages.pages.materialisation.onlyApproved}</p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <p className="text-sm font-medium">{messages.pages.materialisation.materialise}</p>
        </CardHeader>
        <CardBody className="flex flex-col gap-3">
          <div className="grid gap-2">
            <Input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={messages.pages.materialisation.notePlaceholder}
            />
          </div>

          {approved === 0 ? (
            <Notice tone="warn">{messages.pages.materialisation.noApproved}</Notice>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => dryRun.mutate()}
              disabled={approved === 0 || dryRun.isPending || apply.isPending}
              variant={preview ? "secondary" : "primary"}
            >
              {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
            </Button>
            <Button
              onClick={() => apply.mutate()}
              disabled={!preview || apply.isPending}
              title={preview ? undefined : messages.pages.materialisation.previewFirst}
            >
              {apply.isPending ? messages.pages.materialisation.materialising : messages.pages.materialisation.materialise}
            </Button>
          </div>

          {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
          {apply.error ? <ErrorState error={apply.error} /> : null}

          {preview ? (
            <div className="flex flex-col gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
              <p className="text-xs font-medium">{messages.pages.materialisation.nothingWritten}</p>
              <ul className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <PreviewNumber label={messages.pages.materialisation.nodesToCreate} value={preview.nodes_to_create} />
                <PreviewNumber label={messages.pages.materialisation.nodesToAdopt} value={preview.nodes_to_adopt} />
                <PreviewNumber label={messages.pages.materialisation.alreadyInTree} value={preview.nodes_already_materialised} />
                <PreviewNumber label={messages.pages.materialisation.documentsToAttach} value={preview.documents_to_attach} />
                <PreviewNumber label={messages.pages.materialisation.documentsPlaced} value={preview.documents_already_placed} />
                <PreviewNumber label={messages.pages.materialisation.remainingOrphans} value={preview.remaining_orphans} />
              </ul>

              {items.some((item) => item.rooted_early) ? (
                <Notice tone="warn">
                  {fill(messages.pages.materialisation.rootedEarly, {
                    count: String(items.filter((item) => item.rooted_early).length),
                  })}
                </Notice>
              ) : null}

              <ul className="divide-y divide-(--color-line) text-xs">
                {visibleItems.map((item) => (
                  <li key={item.code} className="flex items-center justify-between gap-2 py-1">
                    <code className="truncate">{item.code}</code>
                    <span className="flex shrink-0 items-center gap-2">
                      <Badge tone={ACTION_TONE[item.action] ?? "neutral"}>{labelOf(ACTION_LABEL, item.action)}</Badge>
                      <span className="tabular-nums text-(--color-muted)">{formatCount(item.document_count)}</span>
                    </span>
                  </li>
                ))}
              </ul>
              {items.length > visibleItems.length ? (
                <Button size="sm" variant="ghost" onClick={() => setShowAllItems(true)}>
                  {fill(messages.pages.materialisation.seeAll, { count: formatCount(items.length) })}
                </Button>
              ) : null}
            </div>
          ) : null}

          {result ? (
            <Notice tone="ok" as="div" className="flex flex-col gap-2">
              <p className="font-medium text-(--color-ok)">
                {fill(messages.pages.materialisation.resultLine, {
                  id: String(result.materialisation_id),
                  created: formatCount(result.created_nodes),
                  adopted: formatCount(result.adopted_nodes),
                  attached: formatCount(result.documents_attached),
                })}
              </p>
              <p className="text-(--color-muted)">{messages.pages.materialisation.resultNote}</p>
              <div>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={undo.isPending}
                  onClick={() => undo.mutate(result.materialisation_id)}
                >
                  {undo.isPending ? messages.pages.materialisation.undoing : messages.pages.materialisation.undoThis}
                </Button>
              </div>
            </Notice>
          ) : null}

          {undo.error ? <ErrorState error={undo.error} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <p className="text-sm font-medium">{messages.pages.materialisation.historyTitle}</p>
        </CardHeader>
        <CardBody className="grid gap-2">
          {/*
            The search is server-side and covers the author and the note: a ledger read one page at a
            time cannot be searched in the browser without lying about what it holds.
          */}
          <Input
            value={logTerm}
            placeholder={messages.pages.materialisation.logPlaceholder}
            onChange={(event) => setLogTerm(event.target.value)}
          />
          {log.isPending ? <Spinner label={messages.pages.materialisation.readingHistory} /> : null}
          {log.error ? <ErrorState error={log.error} /> : null}
          {log.data && log.data.items.length === 0 ? (
            <EmptyState
              title={
              term
                ? fill(messages.pages.materialisation.emptyTitleTerm, { term })
                : messages.pages.materialisation.emptyTitleNone
            }
              hint={
                term
                  ? messages.pages.materialisation.emptyHintTerm
                  : messages.pages.materialisation.emptyHintNone
              }
            />
          ) : null}
          <ul className="flex flex-col gap-2">
            {log.data?.items.map((entry) => (
              <li key={entry.materialisation_id} className="rounded-md px-2 py-2 text-xs ring-1 ring-(--color-line)">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">#{entry.materialisation_id}</span>
                  {entry.undone_at ? (
                    <Badge tone="neutral">
                      {fill(messages.pages.materialisation.undoneAt, {
                        date: formatDateTime(entry.undone_at),
                      })}
                    </Badge>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={undo.isPending}
                      onClick={() => undo.mutate(entry.materialisation_id)}
                    >
                      Desfazer
                    </Button>
                  )}
                </div>
                <p className="text-(--color-muted)">
                  {fill(messages.pages.materialisation.changedRows, {
                    date: formatDateTime(entry.changed_at),
                    count: formatCount(entry.changed_rows),
                  })}
                  {entry.changed_by
                    ? fill(messages.pages.materialisation.byAuthor, { name: entry.changed_by })
                    : ""}
                </p>
                {entry.note ? <p className="text-(--color-muted)">{entry.note}</p> : null}
              </li>
            ))}
          </ul>
          {log.data && (log.data.total > log.data.items.length || term) ? (
            <div className="flex items-center gap-2">
              {log.data.total > log.data.items.length ? (
                <Button size="sm" variant="ghost" onClick={() => setLogLimit((current) => current + 10)}>
                  {messages.pages.materialisation.seeMore}
                </Button>
              ) : null}
              <span className="text-xs text-(--color-muted)">
                {fill(messages.pages.materialisation.showing, {
                  shown: formatCount(log.data.items.length),
                  total: formatCount(log.data.total),
                  noun: term
                    ? messages.pages.materialisation.foundBySearch
                    : messages.pages.materialisation.allMaterialisations,
                })}
              </span>
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

function PreviewNumber({ label, value }: { label: string; value: number }) {
  return (
    <li className="flex justify-between gap-2">
      <span className="text-(--color-muted)">{label}</span>
      <span className="font-medium tabular-nums">{formatCount(value)}</span>
    </li>
  );
}

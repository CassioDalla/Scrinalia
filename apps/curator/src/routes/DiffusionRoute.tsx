import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { undoPublicationBatch, type PublicationScope } from "@/api/client";
import { queries } from "@/api/queries";
import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { BatchHistory } from "@/components/publication/BatchHistory";
import { BranchPicker, type BranchChoice } from "@/components/publication/BranchPicker";
import { PublicationList } from "@/components/publication/PublicationList";
import { PublicationPanel, type PublicationPanelRequest } from "@/components/publication/PublicationPanel";
import { ScopeList } from "@/components/publication/ScopeList";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Notice } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { formatCount } from "@/lib/format";
import { nodeLabel } from "@/lib/hierarchy";
import { asString } from "@/lib/search";

const routeApi = getRouteApi("/difusao");

const TABS = ["aPublicar", "publicadas", "ramos", "historico"] as const;
type PublicationTab = (typeof TABS)[number];

export type DiffusionSearch = { aba?: PublicationTab; ramo?: string };

/** The tab and the branch live in the URL: a link to "Publicadas do Fundo A" is a link. */
export function validateDiffusionSearch(search: Record<string, unknown>): DiffusionSearch {
  const aba = asString(search.aba);
  return {
    aba: TABS.includes(aba as PublicationTab) ? (aba as PublicationTab) : undefined,
    ramo: asString(search.ramo),
  };
}

/**
 * Difusão: what the archive exposes, and where.
 *
 * The page has four views over one decision: the approved records no channel carries ("A publicar"),
 * what the channels carry ("Publicadas"), the scopes that decide it ("Publicações por ramo") and the
 * ledger ("Histórico"). The write is one panel — channels, preview, confirm — and the undo is the
 * history's, because the batch is the reversible unit (principle VI).
 *
 * The header's numbers come from the summary route, not from the list: the page shows the same four
 * counts on every tab, and asking a list for its header would put a page of descriptions on the way
 * to a number.
 */
export function DiffusionRoute() {
  const messages = useCopy();
  const copy = messages.pages.publication;
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const aba: PublicationTab = search.aba ?? "aPublicar";
  const ramo = search.ramo;

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [panel, setPanel] = useState<PublicationPanelRequest | null>(null);
  const [picking, setPicking] = useState(false);
  const [undoResult, setUndoResult] = useState<string | null>(null);

  const summary = useQuery(queries.publicationSummary());
  const channelsQuery = useQuery(queries.diffusionChannels());
  const toPublish = useQuery(queries.publications("uncovered", ramo));
  const published = useQuery(queries.publications("covered", ramo));
  const scopes = useQuery(queries.publicationScopes());
  const batches = useQuery(queries.publicationBatches());
  const node = useQuery({ ...queries.node(ramo ?? ""), enabled: Boolean(ramo) });

  const configured = (channelsQuery.data?.channels ?? []).filter((channel) => channel.configured);
  const enabled = configured.filter((channel) => channel.enabled);
  const counts = summary.data;
  const status = counts
    ? fill(copy.statusCounts, {
        site: formatCount(counts.site),
        channels: formatCount(counts.in_channels),
        approved: formatCount(counts.approved_without_channel),
        review: formatCount(counts.in_review),
      })
    : undefined;
  const ramoTitle = ramo ? (node.data?.node ? nodeLabel(node.data.node) : ramo) : null;

  const undo = useMutation({
    mutationFn: (batchId: number) => undoPublicationBatch(batchId),
    onSuccess: (result) => {
      setUndoResult(
        fill(copy.history.undoneResult, {
          restored: formatCount(result.restored),
          skipped: formatCount(result.skipped),
        }),
      );
      queryClient.invalidateQueries({ queryKey: ["diffusion"] });
    },
  });

  const setTab = (id: string) => navigate({ to: "/difusao", search: { ...search, aba: id as PublicationTab } });
  const pickBranch = (choice: BranchChoice) => {
    setPicking(false);
    setSelected(new Set());
    navigate({ to: "/difusao", search: { ...search, ramo: choice?.id } });
  };
  const toggle = (descriptionId: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(descriptionId)) next.delete(descriptionId);
      else next.add(descriptionId);
      return next;
    });
  const toggleAll = () => {
    const ids = (toPublish.data?.items ?? []).map((item) => item.description_id);
    const all = ids.length > 0 && ids.every((id) => selected.has(id));
    setSelected(all ? new Set() : new Set(ids));
  };

  const openScope = (scope: PublicationScope) => {
    setPanel({
      action: scope.kind === "INCLUSION" ? "REVOKE" : "UNEXCLUDE",
      mode: "BRANCH",
      nodeId: scope.node_id,
      channels: [scope.channel_code],
    });
  };

  const items = aba === "publicadas" ? (published.data?.items ?? []) : (toPublish.data?.items ?? []);
  const pageQuery = aba === "publicadas" ? published : toPublish;

  return (
    <>
      <PageHeader
        screen="diffusion"
        status={status}
        pending={summary.isPending}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {ramoTitle ? (
              <Badge tone="accent">
                {fill(copy.filter.chip, { title: ramoTitle })}
                <button
                  className="ml-1 underline"
                  onClick={() => navigate({ to: "/difusao", search: { ...search, ramo: undefined } })}
                >
                  {copy.filter.clear}
                </button>
              </Badge>
            ) : null}
            <Button size="sm" variant="secondary" onClick={() => setPicking(true)}>
              {copy.filter.choose}
            </Button>
          </div>
        }
      />

      <PageBody className="gap-3">
        {configured.length === 0 ? <Notice tone="warn">{copy.noChannel}</Notice> : null}
        {summary.error ? <ErrorState error={summary.error} /> : null}

        <Tabs
          items={[
            { id: "aPublicar", label: copy.tabs.toPublish, hint: copy.tabHints.toPublish },
            { id: "publicadas", label: copy.tabs.published, hint: copy.tabHints.published },
            { id: "ramos", label: copy.tabs.branches, hint: copy.tabHints.branches },
            { id: "historico", label: copy.tabs.history, hint: copy.tabHints.history },
          ]}
          active={aba}
          onChange={setTab}
        />

        {pageQuery.error ? <ErrorState error={pageQuery.error} /> : null}
        {scopes.error ? <ErrorState error={scopes.error} /> : null}
        {batches.error ? <ErrorState error={batches.error} /> : null}
        {undo.error ? <ErrorState error={undo.error} /> : null}
        {undoResult ? <Notice tone="ok">{undoResult}</Notice> : null}

        {aba === "aPublicar" ? (
          <section className="grid gap-3">
            <Notice tone="neutral">{copy.toPublish.hint}</Notice>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="primary"
                disabled={!ramo}
                onClick={() =>
                  setPanel({ action: "PUBLISH", mode: "BRANCH", nodeId: ramo, includeDescendants: true })
                }
              >
                {copy.toPublish.publishBranch}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={selected.size === 0}
                onClick={() => setPanel({ action: "PUBLISH", mode: "RECORDS", descriptionIds: [...selected] })}
              >
                {copy.toPublish.publishSelected}
              </Button>
              <span className="text-xs text-(--color-muted)">
                {fill(copy.toPublish.selected, { count: formatCount(selected.size) })}
              </span>
              {!ramo ? <span className="text-xs text-(--color-muted)">{copy.toPublish.branchMissing}</span> : null}
            </div>
            {toPublish.isPending ? <Skeleton className="h-40" /> : null}
            {toPublish.data && items.length === 0 ? (
              <EmptyState title={copy.toPublish.emptyTitle} hint={copy.toPublish.emptyHint} />
            ) : null}
            {items.length > 0 ? (
              <PublicationList items={items} selected={selected} onToggle={toggle} onToggleAll={toggleAll} />
            ) : null}
          </section>
        ) : null}

        {aba === "publicadas" ? (
          <section className="grid gap-3">
            <Notice tone="neutral">{copy.published.hint}</Notice>
            {published.isPending ? <Skeleton className="h-40" /> : null}
            {published.data && items.length === 0 ? (
              <EmptyState title={copy.published.emptyTitle} hint={copy.published.emptyHint} />
            ) : null}
            {items.length > 0 ? (
              <PublicationList
                items={items}
                renderAction={(item) => (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      setPanel({
                        action: "EXCLUDE",
                        mode: "RECORDS",
                        descriptionIds: [item.description_id],
                        channels: item.channels,
                      })
                    }
                  >
                    {copy.published.keepPrivate}
                  </Button>
                )}
              />
            ) : null}
          </section>
        ) : null}

        {aba === "ramos" ? (
          <section className="grid gap-3">
            <Notice tone="neutral">{copy.branches.hint}</Notice>
            {scopes.isPending ? <Skeleton className="h-40" /> : null}
            {scopes.data && (scopes.data.scopes ?? []).length === 0 ? (
              <EmptyState title={copy.branches.emptyTitle} hint={copy.branches.emptyHint} />
            ) : null}
            {(scopes.data?.scopes ?? []).length > 0 ? (
              <ScopeList scopes={scopes.data?.scopes ?? []} onAction={openScope} />
            ) : null}
          </section>
        ) : null}

        {aba === "historico" ? (
          <section className="grid gap-3">
            <Notice tone="neutral">{copy.history.hint}</Notice>
            {batches.isPending ? <Skeleton className="h-40" /> : null}
            {batches.data && (batches.data.batches ?? []).length === 0 ? (
              <EmptyState title={copy.history.emptyTitle} hint={copy.history.emptyHint} />
            ) : null}
            {(batches.data?.batches ?? []).length > 0 ? (
              <BatchHistory
                batches={batches.data?.batches ?? []}
                onUndo={(batchId) => undo.mutate(batchId)}
                pending={undo.isPending}
              />
            ) : null}
          </section>
        ) : null}
      </PageBody>

      {picking ? <BranchPicker onPick={pickBranch} onClose={() => setPicking(false)} /> : null}

      {panel ? (
        <PublicationPanel
          request={panel}
          channels={configured.length > 0 ? configured : enabled}
          onClose={() => {
            setPanel(null);
            setSelected(new Set());
          }}
        />
      ) : null}
    </>
  );
}

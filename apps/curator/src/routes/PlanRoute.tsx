import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import {
  decideHierarchyPlan,
  suggestHierarchyPlans,
  type DescriptionLevel,
  type HierarchyNodePlan,
  type PlanStatus,
} from "@/api/client";
import { queries } from "@/api/queries";
import { MaterialisationPanel } from "@/components/hierarchy/MaterialisationPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import type { Messages } from "@/i18n/pt";
import { Trans } from "@/i18n/trans";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDateTime } from "@/lib/format";
import {
  PLAN_FLAG_HINT,
  PLAN_FLAG_LABEL,
  PLAN_STATUS_LABEL,
  PLAN_STATUS_TONE,
  labelOf,
} from "@/lib/hierarchy";
import { buildPlanTree, decidedBranchCodes, planRows, type PlanNode, type PlanRow } from "@/lib/hierarchyTree";
import { asEnum, asString } from "@/lib/search";

const routeApi = getRouteApi("/arranjo/plano");

/**
 * How far a rung is indented before the indent stops growing.
 *
 * The tree is the hierarchy — a Dossiê under a Série under a Fundo used to render as three
 * identical cards — but the real catalogue reaches a dozen levels and an uncapped indent would push
 * the text off the screen. Past the cap the row keeps the depth in its metadata and says so on hover.
 */
const MAX_INDENT_DEPTH = 6;

/** How far one nested list shifts the next level. */
const INDENT_STEP = 18;

/**
 * The URL is the state, as in the collection list: the tab, the flag filter, the code search and the
 * branches the archivist closed all live in the query string, so a colleague receives the exact
 * slice of the plan under discussion — including which branches are out of the way.
 *
 * The search is applied locally because the whole catalogue is ~52 rungs and reading it once is
 * cheaper than a request per keystroke — and because the tree needs the ancestors, which a status
 * tab fetched alone would leave out.
 */
export type PlanSearch = { status?: PlanStatus; flag?: string; q?: string; recolhidos?: string };

const STATUSES: PlanStatus[] = ["SUGGESTED", "APPROVED", "REJECTED"];

export function validatePlanSearch(search: Record<string, unknown>): PlanSearch {
  return {
    status: asEnum(search.status, STATUSES),
    flag: asString(search.flag),
    q: asString(search.q),
    recolhidos: asString(search.recolhidos),
  };
}

/** The id the branch toggle points at with ``aria-controls``. */
function childrenId(planId: number): string {
  return `plan-children-${planId}`;
}

function splitCollapsed(value: string | undefined): Set<string> {
  return new Set(
    (value ?? "")
      .split(",")
      .map((code) => code.trim())
      .filter(Boolean),
  );
}

function collapsedParam(codes: ReadonlySet<string>, tree: readonly PlanNode[]): string | undefined {
  const ordered = [...pruneNestedCodes(codes, tree)].sort((left, right) => left.localeCompare(right));
  return ordered.length > 0 ? ordered.join(",") : undefined;
}

/**
 * Only the top of each collapsed branch goes into the URL.
 *
 * "Recolher tudo" closes every branch; writing every code would put a kilobyte in the URL for a
 * result the roots already describe. A code under another collapsed code is dropped.
 */
function pruneNestedCodes(codes: ReadonlySet<string>, tree: readonly PlanNode[]): Set<string> {
  const parentOf = new Map<string, string | null>();
  const collect = (node: PlanNode, parent: string | null) => {
    parentOf.set(node.plan.code, parent);
    for (const child of node.children) collect(child, node.plan.code);
  };
  for (const root of tree) collect(root, null);

  const roots = new Set<string>();
  for (const code of codes) {
    let parent = parentOf.get(code) ?? null;
    let covered = false;
    while (parent !== null) {
      if (codes.has(parent)) {
        covered = true;
        break;
      }
      parent = parentOf.get(parent) ?? null;
    }
    if (!covered) roots.add(code);
  }
  return roots;
}

/** "12 degraus ocultos · 4 aguardando decisão", with the singular for a branch of one. */
function hiddenSentence(
  hidden: number,
  pending: number,
  copy: Messages["pages"]["plan"]["hidden"],
): string {
  const rungs = hidden === 1 ? copy.one : fill(copy.many, { count: formatCount(hidden) });
  const waiting = pending === 1 ? copy.pendingOne : fill(copy.pendingMany, { count: formatCount(pending) });
  return fill(copy.sentence, { rungs, waiting });
}

export function PlanRoute() {
  const messages = useCopy();
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const plans = useQuery(queries.plans());
  const vocabulary = useQuery(queries.hierarchyVocabulary());
  const levels = useQuery(queries.levels());

  const suggest = useMutation({
    mutationFn: suggestHierarchyPlans,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["hierarchy", "plans"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    },
  });

  const patch = (changes: Partial<PlanSearch>) => navigate({ to: "/arranjo/plano", search: { ...search, ...changes } });

  const all = useMemo(() => plans.data?.items ?? [], [plans.data]);
  const tree = useMemo(() => buildPlanTree(all), [all]);
  const collapsed = useMemo(() => splitCollapsed(search.recolhidos), [search.recolhidos]);
  const filters = useMemo(
    () => ({ status: search.status, flag: search.flag, q: search.q }),
    [search.status, search.flag, search.q],
  );
  const rows = useMemo(() => planRows(tree, collapsed, filters), [tree, collapsed, filters]);
  const rowsByCode = useMemo(() => new Map(rows.map((row) => [row.node.plan.code, row])), [rows]);
  const matching = rows.filter((row) => row.matches).length;
  const filterActive = Boolean(search.status || search.flag || search.q);
  const decided = useMemo(() => decidedBranchCodes(tree), [tree]);
  const decidedVisible = useMemo(
    () =>
      new Set(
        [...decided].filter((code) => {
          const row = rowsByCode.get(code);
          return row !== undefined && !row.forced;
        }),
      ),
    [decided, rowsByCode],
  );

  const statusCounts = plans.data?.status_counts ?? {};
  /**
   * The catalogue, not the page.
   *
   * ``status_counts`` covers the **whole** catalogue by contract — that is what lets "24 de 81
   * decididos" be true on a screen that only reads one page — while ``total`` counts the rows the
   * current filter matched. Feeding ``total`` to the progress panel made it say "0 de 57 decididos"
   * the moment a status tab was opened, and made an empty *filter* announce that the catalogue was
   * empty and invite the archivist to propose levels that already exist.
   */
  const catalogueTotal = Object.values(statusCounts).reduce((sum, count) => sum + count, 0);
  const flags = vocabulary.data?.plan_flags ?? [];
  const allCodes = useMemo(() => all.map((item) => item.code), [all]);

  const setCollapsedCodes = (codes: ReadonlySet<string>) =>
    navigate({
      to: "/arranjo/plano",
      search: { ...search, recolhidos: collapsedParam(codes, tree) },
      replace: true,
    });

  const toggleBranch = (code: string) => {
    const next = new Set(collapsed);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setCollapsedCodes(next);
  };

  const expandAll = () => setCollapsedCodes(new Set());
  const collapseAll = () =>
    setCollapsedCodes(new Set(rows.filter((row) => row.hasChildren && !row.forced).map((row) => row.node.plan.code)));
  const collapseDecided = () => setCollapsedCodes(decidedVisible);
  const clearFilters = () => navigate({ to: "/arranjo/plano", search: { recolhidos: search.recolhidos } });

  return (
    <>
      <PageHeader
        screen="plan"
        pending={plans.isPending}
        status={
          plans.data ? (
            <>
              {search.status
                ? fill(messages.pages.plan.statusWithFilter, {
                    matching: formatCount(matching),
                    total: formatCount(catalogueTotal),
                    status: labelOf(PLAN_STATUS_LABEL, search.status),
                  })
                : fill(messages.pages.plan.status, {
                    matching: formatCount(matching),
                    total: formatCount(catalogueTotal),
                  })}
            </>
          ) : undefined
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/*
              The plan only decides the rungs the slicer proposed out of the reference codes. A fund
              or a series with no documents yet has no code to be sliced, so declaring it by hand is
              the *other* write — it lives on the tree screen, and saying so here is the difference
              between "the button is missing" and "the button is next door".
            */}
            <Link to="/acervo/arvore">
              <Button size="sm" variant="secondary" title={messages.pages.plan.createNodeTitle}>
                {messages.pages.plan.createNode}
              </Button>
            </Link>
            <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
              {suggest.isPending ? messages.pages.plan.suggesting : messages.pages.plan.suggest}
            </Button>
          </div>
        }
      />

      <div className="flex min-h-0">
        <div className="min-w-0 flex-1 px-6 py-5">
          <p className="mb-4 max-w-3xl text-sm text-(--color-muted)">
            {messages.pages.plan.intro}
          </p>

          {suggest.data ? (
            <Notice tone="ok" className="mb-4">
              {fill(messages.pages.plan.suggestion, {
                created: formatCount(suggest.data.created),
                refreshed: formatCount(suggest.data.refreshed),
                preserved: formatCount(suggest.data.preserved),
                total: formatCount(suggest.data.total),
              })}
            </Notice>
          ) : null}
          {suggest.error ? <ErrorState error={suggest.error} /> : null}

          <div className="flex flex-wrap items-center gap-2 pb-2">
            <Button size="sm" variant={search.status ? "secondary" : "primary"} onClick={() => patch({ status: undefined })}>
              {messages.pages.textTemplates.allStatuses} {plans.data ? `(${formatCount(catalogueTotal)})` : ""}
            </Button>
            {(vocabulary.data?.plan_statuses ?? STATUSES).map((status) => (
              <Button
                key={status}
                size="sm"
                variant={search.status === status ? "primary" : "secondary"}
                onClick={() => patch({ status: status as PlanStatus })}
              >
                {labelOf(PLAN_STATUS_LABEL, status)} ({formatCount(statusCounts[status] ?? 0)})
              </Button>
            ))}
            <Select
              className="w-52"
              value={search.flag ?? ""}
              onChange={(event) => patch({ flag: event.target.value || undefined })}
            >
              <option value="">{messages.pages.plan.filters.allFlags}</option>
              {flags.map((flag) => (
                <option key={flag} value={flag}>
                  {labelOf(PLAN_FLAG_LABEL, flag)}
                </option>
              ))}
            </Select>
            <Input
              className="max-w-xs"
              placeholder={messages.pages.plan.filters.codePlaceholder}
              defaultValue={search.q ?? ""}
              onChange={(event) => patch({ q: event.target.value || undefined })}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 pb-3">
            <span className="text-xs text-(--color-muted)">{messages.pages.plan.filters.branches}</span>
            <Button size="sm" variant="ghost" onClick={expandAll} disabled={collapsed.size === 0}>
              {messages.pages.plan.filters.expandAll}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={collapseAll}
              disabled={!rows.some((row) => row.hasChildren && !row.forced)}
            >
              {messages.pages.plan.filters.collapseAll}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={collapseDecided}
              disabled={decidedVisible.size === 0}
              title={messages.pages.plan.filters.collapseDecidedTitle}
            >
              {messages.pages.plan.filters.collapseDecided}
            </Button>
          </div>

          {filterActive ? (
            <p className="pb-3 text-xs text-(--color-muted)">
              {messages.pages.plan.filters.notice}
            </p>
          ) : null}

          {plans.error ? <ErrorState error={plans.error} /> : null}
          {plans.isPending ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-28" />
              ))}
            </div>
          ) : null}

          {plans.data && catalogueTotal === 0 ? (
            <EmptyState
              title={messages.pages.plan.empty.noneTitle}
              hint={messages.pages.plan.empty.noneHint}
              action={
                <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
                  {messages.pages.plan.suggest}
                </Button>
              }
            />
          ) : null}

          {plans.data && catalogueTotal > 0 && matching === 0 ? (
            <EmptyState
              title={messages.pages.plan.empty.filteredTitle}
              hint={messages.pages.plan.empty.filteredHint}
              action={
                <Button size="sm" onClick={clearFilters}>
                  {messages.pages.plan.empty.clearFilters}
                </Button>
              }
            />
          ) : null}

          {/*
            The indentation is the hierarchy. A rung carries ``depth`` and ``parent_code``, and the
            flat list used to render a Dossiê and the Fundo above it as two identical cards — the
            archivist could not see which one contains which. Nested lists give the relation real
            markup, and the indent is capped so the deepest rungs do not run off the page; the cap is
            stated in the row's title rather than silent.
          */}
          {plans.data && matching > 0 ? (
            <PlanBranch
              nodes={tree}
              rowsByCode={rowsByCode}
              levels={levels.data ?? []}
              allCodes={allCodes}
              depth={0}
              onToggle={toggleBranch}
            />
          ) : null}
        </div>

        <aside className="w-[380px] shrink-0 overflow-y-auto border-l border-(--color-line) bg-(--color-surface) px-4 py-5">
          <MaterialisationPanel totalPlans={catalogueTotal} statusCounts={statusCounts} />
        </aside>
      </div>
    </>
  );
}

/**
 * One level of the forest, as a real list.
 *
 * A collapsed branch is hidden with CSS rather than unmounted: the card's decision body and anything
 * typed in its form are local state, and unmounting would throw them away the moment a sibling
 * branch closes. The child ``<ul>`` keeps its id, so the toggle's ``aria-controls`` still points at
 * it while it is out of sight.
 */
function PlanBranch({
  nodes,
  rowsByCode,
  levels,
  allCodes,
  depth,
  onToggle,
  id,
}: {
  nodes: PlanNode[];
  rowsByCode: ReadonlyMap<string, PlanRow>;
  levels: DescriptionLevel[];
  allCodes: string[];
  depth: number;
  onToggle: (code: string) => void;
  id?: string;
}) {
  const messages = useCopy();
  const shown = nodes.filter((node) => rowsByCode.has(node.plan.code));
  if (shown.length === 0) return null;

  const indent = depth > 0 && depth <= MAX_INDENT_DEPTH ? INDENT_STEP : 0;

  return (
    <ul
      id={id}
      className={indent > 0 ? "flex flex-col gap-2 border-l border-(--color-line)" : "flex flex-col gap-2"}
      style={indent > 0 ? { paddingLeft: indent } : undefined}
    >
      {shown.map((node) => {
        const row = rowsByCode.get(node.plan.code);
        if (!row) return null;

        return (
          <li
            key={node.plan.code}
            title={
              depth > MAX_INDENT_DEPTH
                ? fill(messages.pages.plan.branch.depthTitle, { depth: node.plan.depth })
                : undefined
            }
          >
            <div className="flex items-start gap-2">
              <div className="w-5 shrink-0 pt-2.5">
                {row.hasChildren && !row.forced ? (
                  <button
                    type="button"
                    onClick={() => onToggle(node.plan.code)}
                    aria-expanded={!row.collapsed}
                    aria-controls={childrenId(node.plan.plan_id)}
                    aria-label={row.collapsed ? messages.pages.plan.branch.expand : messages.pages.plan.branch.collapse}
                    title={row.collapsed ? messages.pages.plan.branch.expand : messages.pages.plan.branch.collapse}
                    className="grid size-5 place-items-center rounded border border-(--color-line) text-[11px] leading-none text-(--color-muted) hover:bg-black/[0.04]"
                  >
                    {row.collapsed ? "+" : "−"}
                  </button>
                ) : null}
              </div>
              <div className="min-w-0 flex-1">
                <PlanCard
                  plan={node.plan}
                  levels={levels}
                  allCodes={allCodes}
                  branchCollapsed={row.collapsed}
                  hidden={row.hidden}
                  hiddenPending={row.hiddenPending}
                />
              </div>
            </div>
            <div className={row.collapsed ? "hidden" : undefined}>
              <PlanBranch
                nodes={node.children}
                rowsByCode={rowsByCode}
                levels={levels}
                allCodes={allCodes}
                depth={depth + 1}
                onToggle={onToggle}
                id={childrenId(node.plan.plan_id)}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * One rung and everything the archivist needs to decide about it.
 *
 * The evidence comes first and the buttons last: the sketch of the screen in the sitemap is explicit
 * that the decision must be taken while looking at `document_count`, the declared levels and the
 * samples, not after scrolling past them. That is why the samples **move into the open body** and the
 * counts stay in the closed row: what closes is the *form*, never the evidence the decision rests on.
 *
 * A suggested rung is ringed, so "what still needs me" reads at a glance in a catalogue of fifty; the
 * decided ones recede. Both collapse to the same shape — code, evidence, decision — because a screen
 * where the undecided rows are the tall ones makes the archivist scroll through forms to find work.
 *
 * The branch collapse and the card disclosure are two different gestures with two different glyphs:
 * the leading gutter closes the rungs below this one, and the card's own chevron opens the decision.
 */
function PlanCard({
  plan,
  levels,
  allCodes,
  branchCollapsed,
  hidden,
  hiddenPending,
}: {
  plan: HierarchyNodePlan;
  levels: DescriptionLevel[];
  allCodes: string[];
  branchCollapsed: boolean;
  hidden: number;
  hiddenPending: number;
}) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const [levelId, setLevelId] = useState<number | null>(plan.level_id ?? null);
  const [title, setTitle] = useState(plan.title ?? "");
  const [collapse, setCollapse] = useState(plan.collapse_into_code ?? "");
  const [note, setNote] = useState(plan.decision_note ?? "");

  const decide = useMutation({
    mutationFn: (status: PlanStatus) =>
      decideHierarchyPlan(plan.plan_id, {
        status,
        level_id: levelId,
        title: title || null,
        collapse_into_code: collapse || null,
        note: note || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["hierarchy", "plans"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    },
  });

  const isSuggested = plan.status === "SUGGESTED";
  const canApprove = levelId !== null;
  const flags = plan.flags ?? [];
  const declaredLevels = plan.declared_levels ?? [];
  const samples = plan.sample_description_ids ?? [];

  return (
    <Disclosure
      className={isSuggested ? "ring-(--color-accent)/40" : undefined}
      toggleLabel={isSuggested ? messages.pages.plan.card.toggleDecide : messages.pages.plan.card.toggleView}
      header={
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <code className="rounded bg-black/[0.05] px-1.5 py-0.5 text-sm">{plan.code}</code>
            <Badge tone={PLAN_STATUS_TONE[plan.status] ?? "neutral"}>{labelOf(PLAN_STATUS_LABEL, plan.status)}</Badge>
            {flags.map((flag) => (
              <Badge key={flag} tone="neutral" title={PLAN_FLAG_HINT[flag]}>
                {labelOf(PLAN_FLAG_LABEL, flag)}
              </Badge>
            ))}
            {plan.materialised_description_id ? <Badge tone="ok">{messages.pages.plan.card.materialised}</Badge> : null}
            {isSuggested ? (
              <span className="text-xs font-medium text-(--color-accent)">{messages.pages.plan.card.awaiting}</span>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-muted)">
            <span>{fill(messages.pages.plan.card.depth, { depth: plan.depth })}</span>
            <span>{fill(messages.pages.plan.card.parent, { parent: plan.parent_code ?? messages.pages.plan.card.root })}</span>
            <span>{fill(messages.pages.plan.card.documents, { count: formatCount(plan.document_count ?? 0) })}</span>
            <span>{fill(messages.pages.plan.card.declaredLevels, { levels: declaredLevels.join(", ") || messages.pages.plan.card.none })}</span>
          </div>

          {!isSuggested ? (
            <p className="text-xs text-(--color-muted)">
              <Trans
                text={messages.pages.plan.card.level}
                values={{ level: <strong className="text-(--color-ink)">{plan.level ?? "—"}</strong> }}
              />
              {plan.title ? fill(messages.pages.plan.card.title, { title: plan.title }) : ""}
              {plan.decided_by ? fill(messages.pages.plan.card.decidedBy, { name: plan.decided_by }) : ""}
              {plan.decided_at ? fill(messages.pages.plan.card.decidedAt, { date: formatDateTime(plan.decided_at) }) : ""}
              {plan.decision_note ? fill(messages.pages.plan.card.note, { note: plan.decision_note }) : ""}
            </p>
          ) : null}

          {plan.collapse_into_code ? (
            <p className="text-xs text-(--color-accent)">
              <Trans
                text={messages.pages.plan.card.collapseInto}
                values={{
                  emphasis: <strong>é</strong>,
                  code: <code>{plan.collapse_into_code}</code>,
                }}
              />
            </p>
          ) : null}

          {branchCollapsed ? (
            <span className="block text-xs text-(--color-muted)">{hiddenSentence(hidden, hiddenPending, messages.pages.plan.hidden)}</span>
          ) : null}
        </div>
      }
      actions={
        isSuggested ? null : (
          <Button
            size="sm"
            variant="ghost"
            disabled={decide.isPending}
            title={messages.pages.plan.card.reopenTitle}
            onClick={() => decide.mutate("SUGGESTED")}
          >
            {messages.pages.plan.card.reopen}
          </Button>
        )
      }
    >
      {samples.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 pb-3 text-xs">
          <span className="text-(--color-muted)">{messages.pages.plan.card.samples}</span>
          {samples.map((id) => (
            <Link
              key={id}
              to="/acervo/$descriptionId"
              params={{ descriptionId: id }}
              className="rounded bg-black/[0.05] px-1 hover:underline"
            >
              {id}
            </Link>
          ))}
        </div>
      ) : null}

      {isSuggested ? (
        <div className="flex flex-col gap-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <Field
              label={
                flags.includes("ORDINAL_INFERRED")
                  ? messages.pages.plan.card.levelInferred
                  : messages.pages.newDescription.levelLabel
              }
            >
              <Select
                value={levelId ?? ""}
                onChange={(event) => setLevelId(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">{messages.pages.plan.card.chooseLevel}</option>
                {levels.map((level) => (
                  <option key={level.level_id} value={level.level_id}>
                    {level.ordinal}. {level.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={messages.pages.plan.card.titleField}>
              <Input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={plan.code}
                maxLength={300}
              />
            </Field>
            <Field label={messages.pages.plan.card.mergeField}>
              <Input
                value={collapse}
                onChange={(event) => setCollapse(event.target.value)}
                placeholder={messages.pages.plan.card.mergePlaceholder}
                list={`codes-${plan.plan_id}`}
                maxLength={500}
              />
              <datalist id={`codes-${plan.plan_id}`}>
                {allCodes
                  .filter((code) => code !== plan.code)
                  .map((code) => (
                    <option key={code} value={code} />
                  ))}
              </datalist>
            </Field>
            <Field label={messages.pages.conflicts.noteField}>
              <Input value={note} onChange={(event) => setNote(event.target.value)} />
            </Field>
          </div>

          {!canApprove ? (
            <p className="text-xs text-(--color-warn)">
              {messages.pages.plan.card.approveNeedsLevel}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={!canApprove || decide.isPending}
              onClick={() => decide.mutate("APPROVED")}
            >
              {decide.isPending ? ACTION.save.pending : messages.pages.textTemplates.approve}
            </Button>
            <Button size="sm" variant="danger" disabled={decide.isPending} onClick={() => decide.mutate("REJECTED")}>
              {messages.pages.textTemplates.reject}
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-(--color-muted)">
          {messages.pages.plan.card.reopenHint}
        </p>
      )}

      {decide.error ? <ErrorState error={decide.error} /> : null}
    </Disclosure>
  );
}

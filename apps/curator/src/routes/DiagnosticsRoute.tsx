import { useQuery } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";

import { queries, DIAGNOSTICS_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { formatCount } from "@/lib/format";
import { DETAIL_LABEL, ISSUE_ACTION, ISSUE_HINT, ISSUE_LABEL, labelOf } from "@/lib/hierarchy";

const routeApi = getRouteApi("/arranjo/diagnostico");

export type DiagnosticsSearch = { issue?: string; offset?: number };

export function validateDiagnosticsSearch(search: Record<string, unknown>): DiagnosticsSearch {
  const offset = typeof search.offset === "string" ? Number(search.offset) : undefined;
  return {
    issue: typeof search.issue === "string" && search.issue.length > 0 ? search.issue : undefined,
    offset: offset !== undefined && Number.isFinite(offset) && offset > 0 ? offset : undefined,
  };
}

/**
 * The structural diagnosis, one section per issue.
 *
 * Three rules shape the screen. The vocabularies come from ``GET /hierarchy/flags`` — and the ones
 * the endpoint lists are exactly the ones ``/diagnostics`` accepts, which is a defect the route used
 * to have. Every section shows the evidence and offers no silent correction: it links to the screen
 * where the fix is a recorded decision. And a section whose count is zero stays visible, because the
 * archivist needs to know the check ran and found nothing.
 */
export function DiagnosticsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const vocabulary = useQuery(queries.hierarchyVocabulary());
  const summary = useQuery(queries.diagnosticSummary());

  const issues = vocabulary.data?.issues ?? [];
  const counts = summary.data?.counts ?? {};

  // A stable default: the first issue that actually has something to show, falling back to the
  // first of the vocabulary while the counts are still loading.
  const firstWithCount = issues.find((issue) => (counts[issue] ?? 0) > 0);
  const issue = search.issue ?? firstWithCount ?? issues[0] ?? "ORPHAN";
  const offset = search.offset ?? 0;

  const page = useQuery(queries.diagnostics(issue, offset));

  const go = (changes: Partial<DiagnosticsSearch>) =>
    navigate({ to: "/arranjo/diagnostico", search: { ...search, ...changes, offset: undefined } });

  const action = ISSUE_ACTION[issue];

  return (
    <>
      <PageHeader
        title="Diagnóstico do arranjo"
        subtitle="Onde o acervo está incoerente. Nenhuma correção acontece sozinha: cada linha mostra a evidência e leva ao lugar onde se decide."
        actions={
          <Link to="/arranjo/plano">
            <Button size="sm">Plano de arranjo</Button>
          </Link>
        }
      />

      <div className="flex min-h-0">
        <aside className="w-80 shrink-0 border-r border-(--color-line) bg-(--color-surface)">
          {summary.isPending ? <Spinner label="Contando os problemas…" /> : null}
          {summary.error ? (
            <div className="p-4">
              <ErrorState error={summary.error} />
            </div>
          ) : null}
          <ul>
            {issues.map((code) => {
              const total = counts[code] ?? 0;
              const active = code === issue;
              return (
                <li key={code}>
                  <button
                    onClick={() => go({ issue: code })}
                    aria-pressed={active}
                    className={
                      "flex w-full items-center justify-between gap-2 border-b border-(--color-line) px-4 py-3 text-left text-sm transition " +
                      (active ? "bg-(--color-accent)/10 font-medium text-(--color-accent)" : "hover:bg-black/[0.03]")
                    }
                  >
                    <span className="min-w-0">
                      <span className="block truncate">{labelOf(ISSUE_LABEL, code)}</span>
                      <code className="block truncate text-[10px] text-(--color-muted)">{code}</code>
                    </span>
                    <span
                      className={
                        "shrink-0 text-sm tabular-nums " +
                        (total === 0 ? "text-(--color-muted)/50" : "font-semibold")
                      }
                    >
                      {formatCount(total)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="px-4 py-3 text-xs text-(--color-muted)">
            As contagens se sobrepõem de propósito — um Dossiê na raiz é ao mesmo tempo{" "}
            <code>ORPHAN</code> e <code>DOSSIER_WITHOUT_PARENT</code> — por isso não há um total geral.
          </p>
        </aside>

        <div className="min-w-0 flex-1 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-3 pb-4">
            <div className="max-w-3xl">
              <h2 className="text-base font-semibold">{labelOf(ISSUE_LABEL, issue)}</h2>
              <p className="mt-1 text-sm text-(--color-muted)">{ISSUE_HINT[issue] ?? ""}</p>
              {action ? <p className="mt-1 text-xs text-(--color-muted)">{action.hint}</p> : null}
            </div>
            <code className="rounded bg-black/[0.05] px-2 py-1 text-xs">{issue}</code>
          </div>

          {page.error ? <ErrorState error={page.error} /> : null}
          {page.isPending ? <Spinner /> : null}

          {page.data && page.data.total === 0 ? (
            <EmptyState
              title="Nenhuma descrição com este problema"
              hint="O diagnóstico rodou e não encontrou nada deste tipo. Isto é o esperado para PATH_DIVERGENCE: a invariante do caminho é garantida por quem escreve."
            />
          ) : null}

          <ul className="flex flex-col gap-2">
            {page.data?.items.map((item) => (
              <li key={item.description_id}>
                <Card>
                  <CardBody className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Link
                        to="/acervo/$descriptionId"
                        params={{ descriptionId: item.description_id }}
                        search={{ aba: "arranjo" }}
                        className="text-sm font-medium hover:underline"
                      >
                        {item.title || item.description_id}
                      </Link>
                      <div className="flex items-center gap-2">
                        {item.level ? <Badge tone="neutral">{item.level}</Badge> : <Badge tone="warn">sem nível</Badge>}
                        <code className="text-xs text-(--color-muted)">{item.description_id}</code>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-muted)">
                      <span>
                        código: <code>{item.reference_code ?? "—"}</code>
                      </span>
                      <span title={item.path}>
                        caminho: <code>{item.path.length > 40 ? `…${item.path.slice(-40)}` : item.path}</code>
                      </span>
                    </div>

                    {(Object.keys(item.detail ?? {}).length > 0) ? (
                      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                        {Object.entries(item.detail ?? {}).map(([key, value]) => (
                          <li key={key}>
                            <span className="text-(--color-muted)">{labelOf(DETAIL_LABEL, key)}: </span>
                            <code>{String(value)}</code>
                          </li>
                        ))}
                      </ul>
                    ) : null}

                    <div>
                      {action?.to ? (
                        <Link to={action.to}>
                          <Button size="sm" variant="secondary">
                            {action.label}
                          </Button>
                        </Link>
                      ) : (
                        <Link
                          to="/acervo/$descriptionId"
                          params={{ descriptionId: item.description_id }}
                          search={{ aba: "arranjo" }}
                        >
                          <Button size="sm" variant="secondary">
                            {action?.label ?? "abrir a descrição"}
                          </Button>
                        </Link>
                      )}
                    </div>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ul>

          {page.data && page.data.total > DIAGNOSTICS_PAGE_SIZE ? (
            <div className="flex items-center justify-between pt-4 text-sm">
              <Button
                size="sm"
                disabled={offset === 0}
                onClick={() => navigate({ to: "/arranjo/diagnostico", search: { issue, offset: Math.max(0, offset - DIAGNOSTICS_PAGE_SIZE) } })}
              >
                ← Anterior
              </Button>
              <span className="text-xs text-(--color-muted)">
                {formatCount(offset + 1)}–{formatCount(Math.min(offset + DIAGNOSTICS_PAGE_SIZE, page.data.total))} de{" "}
                {formatCount(page.data.total)}
              </span>
              <Button
                size="sm"
                disabled={offset + DIAGNOSTICS_PAGE_SIZE >= page.data.total}
                onClick={() =>
                  navigate({
                    to: "/arranjo/diagnostico",
                    search: { issue, offset: offset + DIAGNOSTICS_PAGE_SIZE },
                  })
                }
              >
                Próxima →
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}

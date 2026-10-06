import { useQuery } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";

import { queries, RUNS_PAGE_SIZE } from "@/api/queries";
import type { WorkerRunStatus } from "@/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Select } from "@/components/ui/Input";
import { formatCount, formatDateTime } from "@/lib/format";
import { asEnum, asNumber, asString } from "@/lib/search";
import { describeConfig, formatDuration, isActiveRun, RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/system";

const routeApi = getRouteApi("/sistema/execucoes");

/** The closed vocabulary of the run lifecycle, read from the contract's enum. */
const RUN_STATUSES: readonly WorkerRunStatus[] = ["QUEUED", "RUNNING", "SUCCESS", "FAILED", "INTERRUPTED"];

export type SystemRunsSearch = { worker?: string; status?: WorkerRunStatus; offset?: number };

export function validateSystemRunsSearch(search: Record<string, unknown>): SystemRunsSearch {
  const offset = asNumber(search.offset);
  return {
    worker: asString(search.worker),
    status: asEnum(search.status, RUN_STATUSES),
    offset: offset !== undefined && offset > 0 ? offset : undefined,
  };
}

/**
 * The execution ledger: what ran, with which configuration, and how it ended.
 *
 * The row keeps the **resolved** configuration the run used, so reading it later still means
 * something after a preset changed in the code. The filters are in the URL, like the collection's,
 * because "look at this failed run" is a link somebody sends.
 */
export function SystemRunsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const offset = search.offset ?? 0;
  const page = useQuery({
    ...queries.systemRuns(search.worker, search.status, offset),
    // A queued or running entry is the only reason the ledger changes by itself.
    refetchInterval: (query) => (query.state.data?.items?.some(isActiveRun) ? 5_000 : false),
  });

  // The catalogue supplies the labels and the filter options. It is read once and kept: this screen
  // does not show the queue counts, so there is no reason to pay for them repeatedly.
  const catalogue = useQuery({
    ...queries.systemWorkers(),
    staleTime: 5 * 60_000,
    refetchInterval: false,
  });

  const patch = (changes: Partial<SystemRunsSearch>) =>
    navigate({ to: "/sistema/execucoes", search: { ...search, ...changes, offset: 0 } });

  const labelOf = (name: string) => (catalogue.data?.workers ?? []).find((worker) => worker.name === name)?.label ?? name;
  const total = page.data?.total ?? 0;
  const items = page.data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Execuções"
        subtitle={page.data ? `${formatCount(total)} execução(ões) registrada(s)` : "Lendo o ledger…"}
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        <p className="text-xs text-(--color-muted)">
          Toda execução entra aqui — pela linha de comando ou pelo painel. O registro guarda a configuração já
          resolvida (preset e modelo), então ele continua legível depois que um preset mudar no código.
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <Select
            className="max-w-64"
            value={search.worker ?? ""}
            onChange={(event) => patch({ worker: event.target.value || undefined })}
          >
            <option value="">todos os workers</option>
            {(catalogue.data?.workers ?? []).map((worker) => (
              <option key={worker.name} value={worker.name}>
                {worker.label}
              </option>
            ))}
          </Select>

          <Select
            className="max-w-48"
            value={search.status ?? ""}
            onChange={(event) => patch({ status: (event.target.value || undefined) as WorkerRunStatus | undefined })}
          >
            <option value="">todos os estados</option>
            {RUN_STATUSES.map((status) => (
              <option key={status} value={status}>
                {RUN_STATUS_LABEL[status]}
              </option>
            ))}
          </Select>

          {search.worker || search.status ? (
            <Button size="sm" variant="ghost" onClick={() => patch({ worker: undefined, status: undefined })}>
              limpar filtros
            </Button>
          ) : null}
        </div>

        {page.error ? <ErrorState error={page.error} /> : null}

        {page.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : null}

        {page.data && total === 0 ? (
          <EmptyState
            title="Nenhuma execução registrada"
            hint="Nada rodou desde que o ledger existe. O botão 'Rodar agora' na tela de workers cria a primeira entrada."
          />
        ) : null}

        <ul className="grid gap-2">
          {items.map((run) => (
            <li key={run.run_id}>
              <Card>
                <CardBody className="grid gap-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <Badge tone={RUN_STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</Badge>
                      <span className="truncate text-sm font-medium">{labelOf(run.worker_name)}</span>
                      <span className="font-mono text-[11px] text-(--color-muted)">{run.worker_name}</span>
                      <Badge tone="neutral">{run.trigger === "API" ? "painel" : "linha de comando"}</Badge>
                    </div>
                    <span className="text-xs text-(--color-muted)">
                      #{run.run_id} · {formatDateTime(run.queued_at)} · {formatDuration(run.duration_ms)}
                    </span>
                  </div>

                  <p className="text-xs text-(--color-muted)">
                    <span className="font-mono">{run.engine_name ?? "sem modelo"}</span>
                    {run.preset ? ` · ${run.preset}` : ""}
                    {run.engine_name ? ` · ${describeConfig(run.config)}` : ""}
                    {run.requested_by ? ` · pedido por ${run.requested_by}` : ""}
                  </p>

                  {run.error ? <p className="text-xs text-(--color-danger)">{run.error}</p> : null}
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>

        {total > RUNS_PAGE_SIZE ? (
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-(--color-muted)">
              {offset + 1}–{Math.min(offset + RUNS_PAGE_SIZE, total)} de {formatCount(total)}
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={offset === 0}
                onClick={() => navigate({ to: "/sistema/execucoes", search: { ...search, offset: Math.max(0, offset - RUNS_PAGE_SIZE) } })}
              >
                anteriores
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={offset + RUNS_PAGE_SIZE >= total}
                onClick={() => navigate({ to: "/sistema/execucoes", search: { ...search, offset: offset + RUNS_PAGE_SIZE } })}
              >
                próximas
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

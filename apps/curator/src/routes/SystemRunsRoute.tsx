import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";

import {
  cancelWorkerRun,
  type FailureGroup,
  type WorkerRun,
  type WorkerRunStatus,
} from "@/api/client";
import { queries, FAILURES_PAGE_SIZE, RUNS_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { formatCount, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/cn";
import { routeMessage } from "@/lib/messages";
import { asEnum, asNumber, asString } from "@/lib/search";
import {
  describeConfig,
  describeOptions,
  FAILURE_SOURCE_LABEL,
  formatDuration,
  isActiveRun,
  isCancelRequested,
  MAX_ATTEMPTS,
  RUN_STATUS_LABEL,
  RUN_STATUS_TONE,
  TRIGGER_LABEL,
} from "@/lib/system";

const routeApi = getRouteApi("/sistema/execucoes");

/** The closed vocabulary of the run lifecycle, read from the contract's enum. */
const RUN_STATUSES: readonly WorkerRunStatus[] = [
  "QUEUED",
  "RUNNING",
  "SUCCESS",
  "FAILED",
  "INTERRUPTED",
  "CANCELLED",
];

export type SystemRunsSearch = {
  worker?: string;
  origin?: string;
  status?: WorkerRunStatus;
  fingerprint?: string;
  offset?: number;
};

export function validateSystemRunsSearch(search: Record<string, unknown>): SystemRunsSearch {
  const offset = asNumber(search.offset);
  return {
    worker: asString(search.worker),
    origin: asString(search.origin),
    status: asEnum(search.status, RUN_STATUSES),
    fingerprint: asString(search.fingerprint),
    offset: offset !== undefined && offset > 0 ? offset : undefined,
  };
}

/**
 * The execution ledger: what ran, with which configuration, and how it ended.
 *
 * The row keeps the **resolved** configuration the run used, so reading it later still means
 * something after a preset changed in the code. The filters are in the URL, like the collection's,
 * because "look at this failed run" is a link somebody sends.
 *
 * The grouped failures sit on top because they answer the question the ledger cannot: forty rows
 * saying the same sentence are one cause, and the ledger alone makes them look like forty problems.
 */
export function SystemRunsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const offset = search.offset ?? 0;
  const page = useQuery({
    ...queries.systemRuns(search.worker, search.status, offset, search.fingerprint, search.origin),
    // A queued or running entry is the only reason the ledger changes by itself.
    refetchInterval: (query) => (query.state.data?.items?.some(isActiveRun) ? 5_000 : false),
  });

  const failures = useQuery(queries.systemFailures(search.worker));

  // The catalogue supplies the labels and the filter options. It is read once and kept: this screen
  // does not show the queue counts, so there is no reason to pay for them repeatedly.
  const catalogue = useQuery({
    ...queries.systemWorkers(),
    staleTime: 5 * 60_000,
    refetchInterval: false,
  });

  // The origin vocabulary is the ingestion screen's read; the ledger reuses it for its own filter, so
  // a run of `ingestion` says *which* origin it processed instead of only its worker name.
  const origins = useQuery({
    ...queries.ingestionOrigins(),
    staleTime: 5 * 60_000,
    refetchInterval: false,
  });

  const patch = (changes: Partial<SystemRunsSearch>) =>
    navigate({ to: "/sistema/execucoes", search: { ...search, ...changes, offset: changes.offset } });

  const labelOf = (name: string) => (catalogue.data?.workers ?? []).find((worker) => worker.name === name)?.label ?? name;
  const total = page.data?.total ?? 0;
  const items = page.data?.items ?? [];

  return (
    <>
      <PageHeader
        screen="runs"
        pending={page.isPending}
        status={page.data ? `${formatCount(total)} execução(ões) registrada(s)` : undefined}
      />

      <PageBody>
        <p className="text-xs text-(--color-muted)">
          Toda execução entra aqui — pela linha de comando ou pelo painel. O registro guarda a configuração já
          resolvida (preset e modelo), então ele continua legível depois que um preset mudar no código.
        </p>

        <FailuresPanel
          groups={failures.data?.items ?? []}
          total={failures.data?.total ?? 0}
          pending={failures.isPending}
          failed={failures.isError}
          selected={search.fingerprint}
          labelOf={labelOf}
          onSelect={(group) =>
            patch({ fingerprint: search.fingerprint === group.fingerprint ? undefined : group.fingerprint })
          }
        />

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
            className="max-w-56"
            value={search.origin ?? ""}
            onChange={(event) => patch({ origin: event.target.value || undefined })}
          >
            <option value="">todas as origens</option>
            {(origins.data?.origins ?? []).map((origin) => (
              <option key={origin.code} value={origin.code}>
                {origin.label}
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

          {search.worker || search.origin || search.status || search.fingerprint ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                patch({ worker: undefined, origin: undefined, status: undefined, fingerprint: undefined })
              }
            >
              limpar filtros
            </Button>
          ) : null}
        </div>

        {search.fingerprint ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-(--color-surface) px-4 py-2 ring-1 ring-(--color-line)">
            <span className="text-xs">
              Só as execuções da causa <span className="font-mono">{search.fingerprint}</span>
            </span>
            <Button size="sm" variant="ghost" onClick={() => patch({ fingerprint: undefined })}>
              ver todas
            </Button>
          </div>
        ) : null}

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
            hint="Nada rodou desde que o ledger existe. O botão 'Enfileirar execução' na tela de workers cria a primeira entrada."
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
                      {run.origin_code ? <Badge tone="accent">origem {run.origin_code}</Badge> : null}
                      {run.trial ? (
                        <Badge
                          tone="accent"
                          title="Um ensaio compara configurações e não escreve no acervo (ADR 0018)."
                        >
                          ensaio
                        </Badge>
                      ) : null}
                      <Badge tone="neutral">{TRIGGER_LABEL[run.trigger]}</Badge>
                    </div>
                    <span className="text-xs text-(--color-muted)">
                      #{run.run_id} · {formatDateTime(run.queued_at)} · {formatDuration(run.duration_ms)}
                    </span>
                  </div>

                  <p className="text-xs text-(--color-muted)">
                    {run.trial ? (
                      <>
                        comparação de configurações · o resultado e a escolha ficam em{" "}
                        <Link to="/configuracoes/workers" className="underline">
                          Configurações › {labelOf(run.worker_name)}
                        </Link>
                      </>
                    ) : (
                      <>
                        <span className="font-mono">{run.engine_name ?? "sem modelo"}</span>
                        {run.preset ? ` · ${run.preset}` : ""}
                        {run.engine_name ? ` · ${describeConfig(run.config)}` : ""}
                      </>
                    )}
                    {run.requested_by ? ` · pedido por ${run.requested_by}` : ""}
                  </p>

                  {/*
                    What the run actually read (#120): the columns, the floor, the cap. It sits on
                    its own line because it is the answer to a different question than "with which
                    model?", and a row older than the column says so instead of guessing. A trial has
                    one options set per configuration, so the aggregate line would be a half-truth.
                  */}
                  {run.trial ? null : (
                    <p className="font-mono text-[11px] text-(--color-muted)">{describeOptions(run.options)}</p>
                  )}

                  {run.attempt > 1 || run.retry_of || (run.not_before && run.status === "QUEUED") ? (
                    <p className="text-xs text-(--color-muted)">
                      {run.attempt > 1 ? `tentativa ${run.attempt}/${MAX_ATTEMPTS}` : ""}
                      {run.retry_of ? `${run.attempt > 1 ? " · " : ""}nova tentativa de #${run.retry_of}` : ""}
                      {run.not_before && run.status === "QUEUED"
                        ? `${run.attempt > 1 || run.retry_of ? " · " : ""}começa em ${formatDateTime(run.not_before)}`
                        : ""}
                    </p>
                  ) : null}

                  {run.runner_id ? (
                    <p className="font-mono text-[11px] text-(--color-muted)">
                      runner {run.runner_id}
                      {run.heartbeat_at ? ` · sinal ${formatDateTime(run.heartbeat_at)}` : ""}
                      {run.lease_expires_at && isActiveRun(run)
                        ? ` · lease até ${formatDateTime(run.lease_expires_at)}`
                        : ""}
                    </p>
                  ) : null}

                  {run.error ? <p className="text-xs text-(--color-danger)">{run.error}</p> : null}

                  <RunCancel run={run} />
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
      </PageBody>
    </>
  );
}

/**
 * The stop of one run: the button, its confirmation, and the pending request.
 *
 * The confirmation is inline and in two steps, the shape the other destructive actions use: closing
 * a run is not deleting a record, so a typed code would be ceremony, but a single click on a page
 * full of rows would stop the wrong execution. The sentence is the honest limit — the current batch
 * is committed, not interrupted — and the row keeps saying "em execução" until the worker honours
 * the request, because releasing the slot before then would let a second run overlap it (#72).
 */
function RunCancel({ run }: { run: WorkerRun }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const cancel = useMutation({
    mutationFn: () => cancelWorkerRun(run.run_id),
    onSuccess: () => {
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["system"] });
    },
    // A 409 means the row finished between the render and the click: refetch so the screen stops
    // offering an action that no longer exists.
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: ["system"] });
    },
  });

  if (!isActiveRun(run)) return null;

  if (isCancelRequested(run)) {
    return (
      <p className="text-xs text-(--color-warn)">
        Cancelamento pedido em {formatDateTime(run.cancel_requested_at)}
        {run.cancel_requested_by ? ` por ${run.cancel_requested_by}` : ""}. A execução para no fim do lote
        atual; o que já foi gravado fica.
      </p>
    );
  }

  return (
    <div className="grid gap-2">
      <div>
        <Button size="sm" variant="danger" onClick={() => setOpen((current) => !current)}>
          {open ? "Fechar" : "Cancelar execução…"}
        </Button>
      </div>

      {open ? (
        <Notice tone="warn" as="div" className="grid gap-2">
          <p>
            A execução para no fim do lote atual e o que já foi gravado fica. Se ela ainda não começou, é
            cancelada agora. O lote em curso não é interrompido: uma passada do modelo não pode ser cortada no
            meio.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
              {cancel.isPending ? "Cancelando…" : "Confirmar cancelamento"}
            </Button>
            <Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={() => setOpen(false)}>
              Voltar
            </Button>
          </div>
          {cancel.error ? <ErrorState error={cancel.error} /> : null}
          {cancel.data ? <p className="text-xs text-(--color-muted)">{routeMessage(cancel.data)}</p> : null}
        </Notice>
      ) : null}
    </div>
  );
}

/**
 * The root causes of the window, grouped by the fingerprint PostgreSQL computes.
 *
 * Forty ledger rows saying the same sentence are one cause, and the ledger alone makes them look like
 * forty problems. Clicking a group filters the ledger below instead of opening a second, competing
 * list — the panel is a summary and the ledger is the detail, and they must not disagree.
 *
 * ``worker`` narrows the panel along with the page, which is why the worker filter is the page's.
 */
function FailuresPanel({
  groups,
  total,
  pending,
  failed,
  selected,
  labelOf,
  onSelect,
}: {
  groups: FailureGroup[];
  total: number;
  pending: boolean;
  failed: boolean;
  selected?: string;
  labelOf: (name: string) => string;
  onSelect: (group: FailureGroup) => void;
}) {
  const shown = groups.slice(0, FAILURES_PAGE_SIZE);

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">Falhas agrupadas por causa</span>
        <span className="text-xs text-(--color-muted)">
          {pending ? "lendo…" : `${formatCount(total)} causa(s) nos últimos 30 dias`}
        </span>
      </CardHeader>
      <CardBody className="grid gap-2">
        {failed ? <p className="text-xs text-(--color-danger)">Não foi possível ler as falhas agrupadas.</p> : null}

        {pending ? <Skeleton className="h-16" /> : null}

        {!pending && !failed && shown.length === 0 ? (
          <p className="text-xs text-(--color-muted)">
            Nenhuma falha na janela. As execuções que falharam e os erros inesperados da API aparecem aqui
            agrupados pela causa, e não linha a linha.
          </p>
        ) : null}

        {shown.map((group) => (
          <button
            key={group.fingerprint}
            type="button"
            onClick={() => onSelect(group)}
            title={group.fingerprint}
            className={cn(
              "grid w-full gap-1 rounded-lg px-3 py-2 text-left ring-1 transition",
              selected === group.fingerprint
                ? "bg-(--color-accent)/10 ring-(--color-accent)/40"
                : "ring-(--color-line) hover:bg-black/[0.03]",
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="min-w-0 flex-1 truncate text-sm">{group.sample}</span>
              <Badge tone={group.occurrences > 1 ? "danger" : "warn"}>{formatCount(group.occurrences)}×</Badge>
            </div>

            <p className="text-xs text-(--color-muted)">
              {group.sources.map((source) => FAILURE_SOURCE_LABEL[source]).join(" · ")}
              {(group.worker_names ?? []).length > 0
                ? ` · ${(group.worker_names ?? []).map(labelOf).join(", ")}`
                : ""}
              {group.last_path ? ` · ${group.last_path}` : ""}
              {` · última em ${formatDateTime(group.last_seen)}`}
            </p>

            {group.last_request_id ? (
              <p className="font-mono text-[11px] text-(--color-muted)">referência: {group.last_request_id}</p>
            ) : null}
          </button>
        ))}

        {shown.length > 0 ? (
          <p className="text-xs text-(--color-muted)">
            Clique numa causa para ver só as execuções dela. A referência de uma falha de API é o que se procura no log.
          </p>
        ) : null}

        {total > shown.length ? (
          <p className="text-xs text-(--color-muted)">
            Há mais {formatCount(total - shown.length)} causa(s) na janela; as mais recentes estão acima.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import {
  deleteIngestionSchedule,
  fetchCurrentUser,
  saveIngestionSchedule,
  triggerIngestionRun,
  updateIngestionOrigin,
  type IngestionOption,
  type IngestionOrigin,
  type OriginAvailable,
  type OriginConfigField,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";
import { SidePanel, SidePanelClose } from "@/components/ui/SidePanel";
import { formatCount, formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/system";

/**
 * Origens: the installation's sources, and the two entry paths beside them.
 *
 * The card answers *which queue is this, what does it read, when does it run and what happened last
 * time* — the operator's question, and the axis #44 added to a panel that used to start at
 * `transfer`. A definition with a row is **configured**; a definition without one is **available**,
 * offered by "Adicionar origem". The manual and CSV rows stay for provenance and for the entry
 * paths, but they are not sources: they come back `configurable=false` and are shown read-only with
 * their own link to `/acervo/nova` (#205/#206).
 */
export function OriginsRoute() {
  const { data, isPending, error } = useQuery({
    ...queries.ingestionOrigins(),
    // A queued run changes when a runner appears; a running one changes every few seconds.
    refetchInterval: (query) =>
      (query.state.data?.origins ?? []).some((origin) => origin.active_run_id != null) ? 5_000 : 15_000,
  });
  const current = useQuery({ queryKey: ["current-user"], queryFn: fetchCurrentUser, retry: false });
  const role = current.data?.role ?? "VIEWER";
  const canOperate = can(role, "OPERATE");

  const [pickerOpen, setPickerOpen] = useState(false);
  const origins = data?.origins ?? [];
  const sources = origins.filter((origin) => origin.configurable);
  const entries = origins.filter((origin) => !origin.configurable);
  const available = data?.available ?? [];
  const active = sources.filter((origin) => origin.enabled).length;

  return (
    <>
      <PageHeader
        screen="origins"
        pending={isPending}
        status={
          sources.length === 0
            ? "Nenhuma origem configurada"
            : `${formatCount(sources.length)} ${sources.length === 1 ? "origem configurada" : "origens configuradas"} · ${formatCount(active)} ${active === 1 ? "ativa" : "ativas"}`
        }
      />

      <PageBody className="gap-3">
        {error ? <ErrorState error={error} /> : null}

        <Card>
          <CardBody className="grid gap-2">
            <p className="text-sm text-(--color-muted)">
              A ingestão lê a origem para o <span className="font-mono text-xs">raw</span>, estrutura o
              resultado no <span className="font-mono text-xs">staging</span> e o deixa pronto para a
              transferência. Cada origem tem a sua fila, a sua agenda e a sua configuração; a IA e o
              painel de workers vêm depois.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {/*
                The two tabs of the merged operations screen (#207), named the way the tab bar names
                them: the panel is the queue side, the ledger is the run history of every worker —
                including this origin's `ingestion` runs.
              */}
              <Link to="/sistema/workers">
                <Button size="sm" variant="secondary">
                  Painel dos workers
                </Button>
              </Link>
              <Link to="/sistema/workers" search={{ aba: "execucoes" }}>
                <Button size="sm" variant="ghost">
                  Execuções
                </Button>
              </Link>
            </div>
          </CardBody>
        </Card>

        <section className="grid gap-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Origens</h2>
              <p className="text-xs text-(--color-muted)">
                As fontes que esta instalação lê: adicione uma definição do pacote, configure, agende,
                pause e enfileire uma execução.
              </p>
            </div>
            {canOperate && available.length > 0 && sources.length > 0 ? (
              <Button size="sm" variant="primary" onClick={() => setPickerOpen(true)}>
                Adicionar origem
              </Button>
            ) : null}
          </div>

          {isPending ? (
            <div className="grid gap-3">
              {Array.from({ length: 2 }).map((_, index) => (
                <Skeleton key={index} className="h-32" />
              ))}
            </div>
          ) : sources.length === 0 ? (
            <EmptyState
              title="Nenhuma origem configurada"
              hint="A instalação ainda não lê nenhum site. Adicione uma origem do pacote; a entrada manual e a importação CSV ficam no Acervo, em Nova descrição."
              action={
                canOperate && available.length > 0 ? (
                  <Button size="sm" variant="primary" onClick={() => setPickerOpen(true)}>
                    Adicionar origem
                  </Button>
                ) : canOperate ? (
                  <p className="text-xs text-(--color-muted)">Todas as origens do pacote já estão configuradas.</p>
                ) : null
              }
            />
          ) : (
            sources.map((origin) => <OriginCard key={origin.code} origin={origin} canOperate={canOperate} />)
          )}

          {!isPending && sources.length > 0 && canOperate && available.length === 0 ? (
            <p className="text-xs text-(--color-muted)">Todas as origens do pacote já estão configuradas.</p>
          ) : null}
        </section>

        {entries.length > 0 ? (
          <section className="grid gap-3">
            <div>
              <h2 className="text-sm font-semibold">Entradas</h2>
              <p className="text-xs text-(--color-muted)">
                A entrada manual e a importação CSV não são origens de leitura: o registro é criado no
                Acervo, e estas linhas só mostram o estado delas.
              </p>
            </div>
            {entries.map((origin) => (
              <EntryCard key={origin.code} origin={origin} />
            ))}
          </section>
        ) : null}
      </PageBody>

      {pickerOpen ? <AddOriginPanel available={available} onClose={() => setPickerOpen(false)} /> : null}
    </>
  );
}

/** The three kinds the registry can produce; the badge says which one this card is. */
const ORIGIN_KIND_LABEL: Record<string, string> = {
  MANUAL: "manual",
  CSV: "csv",
  SCRAPER: "scraper",
};

function OriginCard({ origin, canOperate }: { origin: IngestionOrigin; canOperate: boolean }) {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"none" | "config" | "schedule">("none");

  const active = origin.active_run_id != null;
  const controlled = canOperate;

  return (
    <Disclosure
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setPanel("none");
      }}
      header={<OriginHeader origin={origin} />}
      actions={
        controlled ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setPanel(panel === "config" ? "none" : "config")}>
              Configurar
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPanel(panel === "schedule" ? "none" : "schedule")}>
              Agenda
            </Button>
            <LifecycleButton origin={origin} />
          </div>
        ) : null
      }
      toggleLabel="Ver fila, execução e configuração"
    >
      <div className="grid gap-3">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <Fact label="Fila">
            <span className="text-2xl leading-none font-semibold tabular-nums">
              {origin.pending == null ? "—" : formatCount(origin.pending)}
            </span>
            <p className="mt-1 text-xs text-(--color-muted)">
              {origin.pending_reason ?? "O que a próxima execução desta origem leria."}
            </p>
          </Fact>
          <Fact label="Processados">
            <span className="text-2xl leading-none font-semibold tabular-nums">
              {origin.processed == null ? "—" : formatCount(origin.processed)}
            </span>
            <p className="mt-1 text-xs text-(--color-muted)">
              {origin.failed ? `${formatCount(origin.failed)} com falha terminal` : "sem falha terminal"}
            </p>
          </Fact>
          <Fact label="Última execução">
            {origin.last_run_id == null ? (
              <span className="text-sm text-(--color-muted)">nenhuma</span>
            ) : (
              <>
                <span className="flex flex-wrap items-center gap-1">
                  {origin.last_run_status ? (
                    <Badge tone={RUN_STATUS_TONE[origin.last_run_status]}>
                      {RUN_STATUS_LABEL[origin.last_run_status]}
                    </Badge>
                  ) : null}
                  <span className="text-xs text-(--color-muted)">#{origin.last_run_id}</span>
                </span>
                <p className="mt-1 text-xs text-(--color-muted)">{formatDateTime(origin.last_run_at)}</p>
                {origin.last_run_error ? (
                  <p className="mt-1 line-clamp-2 text-xs text-(--color-danger)">{origin.last_run_error}</p>
                ) : null}
              </>
            )}
          </Fact>
          <Fact label="Agenda">
            {origin.schedule?.cron ? (
              <>
                <span className="font-mono text-xs">{origin.schedule.cron}</span>
                <p className="mt-1 text-xs text-(--color-muted)">
                  {origin.schedule.timezone} · próxima {formatDateTime(origin.schedule.next_run_at)}
                </p>
              </>
            ) : (
              <span className="text-sm text-(--color-muted)">sem agenda</span>
            )}
          </Fact>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {controlled ? (
            <RunNowButton origin={origin} disabled={active} />
          ) : (
            <p className="text-xs text-(--color-muted)">A configuração, a agenda e a execução são do operador.</p>
          )}
          {active ? (
            <Badge tone="accent">
              {origin.active_run_status ? RUN_STATUS_LABEL[origin.active_run_status] : "em execução"} #{origin.active_run_id}
            </Badge>
          ) : null}
          {origin.runner_available ? (
            <Badge tone="ok">runner disponível</Badge>
          ) : (
            <Badge tone="warn">nenhum runner aceita ingestão</Badge>
          )}
        </div>

        {panel === "config" && controlled ? <OriginConfigForm origin={origin} /> : null}
        {panel === "schedule" && controlled ? <OriginScheduleForm origin={origin} /> : null}
      </div>
    </Disclosure>
  );
}

function OriginHeader({ origin }: { origin: IngestionOrigin }) {
  return (
    <div className="grid gap-0.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{origin.label}</span>
        <Badge tone="neutral">{ORIGIN_KIND_LABEL[origin.kind] ?? origin.kind.toLowerCase()}</Badge>
        <Badge tone={origin.enabled ? "ok" : "neutral"}>{origin.enabled ? "ativa" : "pausada"}</Badge>
        <span className="text-xs text-(--color-muted)">{origin.description}</span>
      </div>
      <span className="text-xs text-(--color-muted)">{configSummary(origin)}</span>
    </div>
  );
}

/** The effective configuration in one muted line; the fields' own help stays in the form. */
function configSummary(origin: IngestionOrigin): string {
  const config = origin.config ?? {};
  const parts = (origin.config_fields ?? []).flatMap((field) => {
    const value = config[field.name];
    if (value === null || value === undefined || value === "") return [];
    return [`${field.label}: ${String(value)}`];
  });
  return parts.length > 0
    ? parts.join(" · ")
    : "Sem configuração própria: o adapter usa os valores do ambiente quando os tem.";
}

/** Pausing is the lifecycle, not a removal: the row, the agenda and the runs stay. */
function LifecycleButton({ origin }: { origin: IngestionOrigin }) {
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: () =>
      updateIngestionOrigin(origin.code, {
        enabled: !origin.enabled,
        config: origin.config ?? {},
        options: origin.options ?? {},
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });

  return (
    <div className="grid gap-1">
      <Button
        size="sm"
        variant={origin.enabled ? "ghost" : "secondary"}
        disabled={toggle.isPending}
        onClick={() => toggle.mutate()}
      >
        {toggle.isPending ? "Salvando…" : origin.enabled ? "Desativar" : "Ativar"}
      </Button>
      {toggle.error ? <ErrorState error={toggle.error} /> : null}
    </div>
  );
}

function RunNowButton({ origin, disabled }: { origin: IngestionOrigin; disabled: boolean }) {
  const queryClient = useQueryClient();
  const run = useMutation({
    mutationFn: () =>
      triggerIngestionRun(origin.code, {
        force_retry_fatal: false,
        ignore_sliding_window: false,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "runs"] });
    },
  });

  const paused = !origin.enabled;
  return (
    <div className="grid gap-1">
      <Button size="sm" variant="primary" disabled={disabled || paused || run.isPending} onClick={() => run.mutate()}>
        {paused ? "Origem pausada" : disabled ? "Já há uma execução" : run.isPending ? "Enfileirando…" : "Enfileirar execução"}
      </Button>
      {run.data ? (
        <span className="text-xs text-(--color-muted)">
          Execução #{run.data.run_id} na fila; um runner a pega quando estiver livre.
        </span>
      ) : null}
      {run.error ? <ErrorState error={run.error} /> : null}
    </div>
  );
}

function OriginConfigForm({ origin }: { origin: IngestionOrigin }) {
  const queryClient = useQueryClient();
  const configFields = origin.config_fields ?? [];
  const optionFields = origin.option_fields ?? [];
  const [config, setConfig] = useState<Record<string, string | number | boolean>>(() =>
    initialConfig(configFields, origin.config ?? {}),
  );
  const [options, setOptions] = useState<Record<string, string | boolean>>(() =>
    initialOptions(optionFields, origin.options ?? {}),
  );

  const save = useMutation({
    mutationFn: () =>
      updateIngestionOrigin(origin.code, {
        // The lifecycle is the card's action, not a second toggle inside the form.
        enabled: origin.enabled,
        config: configValues(configFields, config),
        options: optionValues(optionFields, options),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });

  return (
    <div className="grid gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      {configFields.length === 0 ? (
        <p className="text-xs text-(--color-muted)">Esta origem não tem configuração de adapter.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {configFields.map((field) => (
            <Field key={field.name} label={field.label}>
              {field.kind === "boolean" ? (
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={Boolean(config[field.name])}
                    onChange={(event) => setConfig({ ...config, [field.name]: event.target.checked })}
                  />
                  {field.help}
                </label>
              ) : (
                <>
                  <Input
                    type={field.kind === "number" ? "number" : "text"}
                    value={String(config[field.name] ?? "")}
                    onChange={(event) => setConfig({ ...config, [field.name]: event.target.value })}
                  />
                  <span className="text-[11px] text-(--color-muted)">{field.help}</span>
                </>
              )}
            </Field>
          ))}
        </div>
      )}

      {optionFields.length > 0 ? (
        <details className="grid gap-2">
          <summary className="cursor-pointer text-xs font-medium">Opções da execução agendada</summary>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {optionFields.map((option) => (
              <Field key={option.name} label={option.label}>
                {option.kind === "boolean" ? (
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={Boolean(options[option.name])}
                      onChange={(event) => setOptions({ ...options, [option.name]: event.target.checked })}
                    />
                    {option.help}
                  </label>
                ) : (
                  <>
                    <Input
                      type="number"
                      value={String(options[option.name] ?? "")}
                      onChange={(event) => setOptions({ ...options, [option.name]: event.target.value })}
                    />
                    <span className="text-[11px] text-(--color-muted)">{option.help}</span>
                  </>
                )}
              </Field>
            ))}
          </div>
        </details>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Salvando…" : "Salvar configuração"}
        </Button>
        {save.data ? <span className="text-xs text-(--color-muted)">Configuração salva.</span> : null}
      </div>
      {save.error ? <ErrorState error={save.error} /> : null}
    </div>
  );
}

function OriginScheduleForm({ origin }: { origin: IngestionOrigin }) {
  const queryClient = useQueryClient();
  const [cron, setCron] = useState(origin.schedule?.cron ?? "0 2 * * *");
  const [timezone, setTimezone] = useState(origin.schedule?.timezone ?? "America/Sao_Paulo");

  const save = useMutation({
    mutationFn: () => saveIngestionSchedule(origin.code, { cron: cron.trim(), timezone: timezone.trim() || null }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteIngestionSchedule(origin.code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });

  return (
    <div className="grid gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <p className="text-xs text-(--color-muted)">
        Cinco campos (minuto, hora, dia do mês, mês, dia da semana), avaliados na zona indicada. Um período
        que chega com uma ingestão ativa é <strong>pulado</strong>, não enfileirado.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Cron">
          <Input value={cron} onChange={(event) => setCron(event.target.value)} placeholder="0 2 * * *" />
        </Field>
        <Field label="Fuso IANA">
          <Input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="America/Sao_Paulo" />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="primary" disabled={save.isPending || cron.trim().length === 0} onClick={() => save.mutate()}>
          {save.isPending ? "Salvando…" : "Salvar agenda"}
        </Button>
        <Button size="sm" variant="ghost" disabled={remove.isPending || !origin.schedule} onClick={() => remove.mutate()}>
          Remover agenda
        </Button>
      </div>
      {save.error ? <ErrorState error={save.error} /> : null}
      {remove.error ? <ErrorState error={remove.error} /> : null}
    </div>
  );
}

/** A manual/CSV entry: its row is kept for provenance, not for the operator to configure. */
function EntryCard({ origin }: { origin: IngestionOrigin }) {
  return (
    <Card>
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{origin.label}</span>
          <Badge tone="neutral">{ORIGIN_KIND_LABEL[origin.kind] ?? origin.kind.toLowerCase()}</Badge>
          <Badge tone={origin.enabled ? "ok" : "neutral"}>{origin.enabled ? "ativa" : "pausada"}</Badge>
          <Badge tone="neutral">não configurável</Badge>
        </div>
        <p className="text-xs text-(--color-muted)">{origin.description}</p>
        {origin.pending ? (
          <p className="text-xs text-(--color-muted)">{formatCount(origin.pending)} na fila de staging.</p>
        ) : null}
        <div>
          <Link to="/acervo/nova" search={origin.kind === "CSV" ? { modo: "csv" } : {}}>
            <Button size="sm" variant="secondary">
              Abrir a entrada
            </Button>
          </Link>
        </div>
      </CardBody>
    </Card>
  );
}

/** The picker: the definitions the package ships and this installation has no row for yet. */
function AddOriginPanel({ available, onClose }: { available: OriginAvailable[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const add = useMutation({
    mutationFn: (code: string) => updateIngestionOrigin(code, { enabled: true, config: {}, options: {} }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
      onClose();
    },
  });

  return (
    <SidePanel
      label="Adicionar origem"
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-(--color-muted)">
            A origem é uma definição do pacote; adicionar só a ativa nesta instalação.
          </span>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Fechar
          </Button>
        </div>
      }
    >
      <div className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Adicionar origem</h2>
            <p className="mt-0.5 text-xs text-(--color-muted)">
              Escolha uma definição que o pacote traz e ainda não está configurada. Adicionar a ativa.
            </p>
          </div>
          <SidePanelClose onClose={onClose} />
        </div>

        {add.error ? <ErrorState error={add.error} /> : null}

        {available.length === 0 ? (
          <EmptyState
            title="Todas as origens já estão configuradas"
            hint="O pacote não tem outra definição de leitura para adicionar."
          />
        ) : (
          available.map((item) => (
            <Card key={item.code}>
              <CardBody className="grid gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{item.label}</span>
                  <Badge tone="neutral">{ORIGIN_KIND_LABEL[item.kind] ?? item.kind.toLowerCase()}</Badge>
                </div>
                <p className="text-xs text-(--color-muted)">{item.description}</p>
                <div>
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={add.isPending}
                    onClick={() => add.mutate(item.code)}
                  >
                    {add.isPending && add.variables === item.code ? "Adicionando…" : "Adicionar"}
                  </Button>
                </div>
              </CardBody>
            </Card>
          ))
        )}
      </div>
    </SidePanel>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md bg-black/[0.02] px-3 py-2 ring-1 ring-(--color-line)">
      <span className="text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">{label}</span>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function initialConfig(fields: OriginConfigField[], values: Record<string, unknown>): Record<string, string | number | boolean> {
  return Object.fromEntries(
    fields.map((field) => {
      const value = values[field.name] ?? field.default ?? "";
      return [field.name, field.kind === "boolean" ? Boolean(value) : typeof value === "number" ? value : String(value)];
    }),
  );
}

function configValues(
  fields: OriginConfigField[],
  values: Record<string, string | number | boolean>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (value === "" || value == null) continue;
    result[field.name] = field.kind === "number" ? Number(value) : value;
  }
  return result;
}

function initialOptions(fields: IngestionOption[], values: Record<string, unknown>): Record<string, string | boolean> {
  return Object.fromEntries(
    fields.map((field) => {
      const value = values[field.name] ?? field.default ?? "";
      return [field.name, field.kind === "boolean" ? Boolean(value) : String(value)];
    }),
  );
}

function optionValues(fields: IngestionOption[], values: Record<string, string | boolean>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (value === "" || value == null) continue;
    if (field.kind === "boolean" && value === false) continue;
    result[field.name] = field.kind === "boolean" ? value : Number(value);
  }
  return result;
}

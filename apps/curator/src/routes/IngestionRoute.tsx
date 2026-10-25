import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import {
  createManualIngestion,
  deleteIngestionSchedule,
  fetchCurrentUser,
  saveIngestionSchedule,
  triggerIngestionRun,
  updateIngestionOrigin,
  type IngestionOption,
  type IngestionOrigin,
  type OriginConfigField,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { can } from "@/lib/permissions";
import { formatCount, formatDateTime } from "@/lib/format";
import { routeMessage } from "@/lib/messages";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/system";

/**
 * Ingestão: the stage in front of the archive, origin by origin.
 *
 * Two questions share this screen because they share the object. The origin cards answer *which queue
 * is this, what does it read and when does it run* — the operator's question, and the axis #44 added
 * to a panel that used to start at `transfer`. The manual form answers *how does an archivist type a
 * record*, and its answer is deliberately the same pipeline: raw -> staging -> transfer -> AI. The
 * submit is not an approval; the archive description is born `PENDING_AI` and the review happens in
 * the dossier after the AI runs.
 */
export function IngestionRoute() {
  const { data, isPending, error } = useQuery({
    ...queries.ingestionOrigins(),
    // A queued run changes when a runner appears; a running one changes every few seconds.
    refetchInterval: (query) =>
      (query.state.data?.origins ?? []).some((origin) => origin.active_run_id != null) ? 5_000 : 15_000,
  });
  const current = useQuery({ queryKey: ["current-user"], queryFn: fetchCurrentUser, retry: false });
  const role = current.data?.role ?? "VIEWER";
  const canOperate = can(role, "OPERATE");
  const canCurate = can(role, "CURATE");

  return (
    <>
      <PageHeader screen="ingestion" />
      <PageBody className="gap-3">
        {error ? <ErrorState error={error} /> : null}

        <Card>
          <CardBody className="grid gap-2">
            <p className="text-sm text-(--color-muted)">
              A ingestão lê a origem para o <span className="font-mono text-xs">raw</span>, estrutura o
              resultado no <span className="font-mono text-xs">staging</span> e o deixa pronto para a
              transferência. A origem tem a sua própria fila, a sua própria agenda e a sua própria
              configuração; a IA e o painel de workers vêm depois.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Link to="/sistema/workers">
                <Button size="sm" variant="secondary">
                  Workers de IA
                </Button>
              </Link>
              <Link to="/sistema/execucoes">
                <Button size="sm" variant="ghost">
                  Execuções
                </Button>
              </Link>
            </div>
          </CardBody>
        </Card>

        {canCurate ? <ManualEntryCard /> : null}

        {isPending ? (
          <div className="grid gap-3">
            {Array.from({ length: 2 }).map((_, index) => (
              <Skeleton key={index} className="h-32" />
            ))}
          </div>
        ) : null}

        {(data?.origins ?? []).map((origin) => (
          <OriginCard key={origin.code} origin={origin} canOperate={canOperate} />
        ))}
      </PageBody>
    </>
  );
}

function ManualEntryCard() {
  const queryClient = useQueryClient();
  const [descriptionId, setDescriptionId] = useState(() => `manual-${crypto.randomUUID()}`);
  const [title, setTitle] = useState("");
  const [referenceCode, setReferenceCode] = useState("");
  const [level, setLevel] = useState("");
  const [documentDate, setDocumentDate] = useState("");
  const [scopeContent, setScopeContent] = useState("");
  const [producers, setProducers] = useState("");
  const [bioHistory, setBioHistory] = useState("");
  const [accessConditions, setAccessConditions] = useState("");
  const [indexingPoints, setIndexingPoints] = useState("");

  const submit = useMutation({
    mutationFn: () =>
      createManualIngestion({
        description_id: descriptionId,
        title: title.trim(),
        reference_code: emptyToNull(referenceCode),
        level: emptyToNull(level),
        document_date: emptyToNull(documentDate),
        scope_content: emptyToNull(scopeContent),
        producers: emptyToNull(producers),
        admin_bio_history: emptyToNull(bioHistory),
        access_conditions: emptyToNull(accessConditions),
        indexing_points: emptyToNull(indexingPoints),
      }),
    onSuccess: () => {
      // The origin's pending count and the ledger both moved: the record is staged and a transfer
      // may have been queued.
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "runs"] });
      setDescriptionId(`manual-${crypto.randomUUID()}`);
    },
  });

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2 text-sm font-semibold">
        <span>Entrada manual</span>
        <Badge tone="accent">PENDING_AI</Badge>
      </CardHeader>
      <CardBody className="grid gap-3">
        <p className="text-xs text-(--color-muted)">
          A descrição digitada aqui <strong>não é uma aprovação</strong>. Ela entra no mesmo staging e na
          mesma fila de IA das demais origens; depois da IA, o dossiê é o lugar de revisar e aprovar.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Título">
            <Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={500} />
          </Field>
          <Field label="Código de referência">
            <Input value={referenceCode} onChange={(event) => setReferenceCode(event.target.value)} />
          </Field>
          <Field label="Nível de descrição">
            <Input value={level} onChange={(event) => setLevel(event.target.value)} placeholder="Ex.: Série" />
          </Field>
          <Field label="Data de produção">
            <Input type="date" value={documentDate} onChange={(event) => setDocumentDate(event.target.value)} />
          </Field>
          <Field label="Produtores">
            <Input value={producers} onChange={(event) => setProducers(event.target.value)} />
          </Field>
          <Field label="Condições de acesso">
            <Input value={accessConditions} onChange={(event) => setAccessConditions(event.target.value)} />
          </Field>
        </div>

        <Field label="Âmbito e conteúdo">
          <Textarea value={scopeContent} onChange={(event) => setScopeContent(event.target.value)} rows={3} />
        </Field>
        <Field label="História administrativa / biográfica">
          <Textarea value={bioHistory} onChange={(event) => setBioHistory(event.target.value)} rows={2} />
        </Field>
        <Field label="Pontos de acesso">
          <Input
            value={indexingPoints}
            onChange={(event) => setIndexingPoints(event.target.value)}
            placeholder="separados por vírgula"
          />
        </Field>

        {submit.data ? (
          <Notice tone="ok" as="div" className="grid gap-1">
            <p className="font-medium">{routeMessage(submit.data)}</p>
            <p className="font-mono text-xs">{submit.data.data.description_id}</p>
            <p>
              O registro aparece no acervo quando a transferência rodar. Até lá, ele está no staging e o
              dossiê ainda pode responder “não encontrado”.
            </p>
            <Link to="/acervo/$descriptionId" params={{ descriptionId: submit.data.data.description_id }}>
              Abrir o dossiê
            </Link>
          </Notice>
        ) : null}
        {submit.error ? <ErrorState error={submit.error} /> : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={title.trim().length === 0 || submit.isPending}
            onClick={() => submit.mutate()}
          >
            {submit.isPending ? "Gravando…" : "Gravar e enviar para a fila"}
          </Button>
          <span className="text-xs text-(--color-muted)">
            id do formulário: <span className="font-mono">{descriptionId}</span>
          </span>
        </div>
      </CardBody>
    </Card>
  );
}

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
            <p className="text-xs text-(--color-muted)">
              A configuração, a agenda e a execução são do operador; a entrada manual está disponível acima.
            </p>
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
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium">{origin.label}</span>
      <Badge tone="neutral">{origin.kind === "MANUAL" ? "manual" : "scraper"}</Badge>
      <Badge tone={origin.enabled ? "ok" : "neutral"}>{origin.enabled ? "ativa" : "pausada"}</Badge>
      <span className="text-xs text-(--color-muted)">{origin.description}</span>
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

  return (
    <div className="grid gap-1">
      <Button size="sm" variant="primary" disabled={disabled || run.isPending} onClick={() => run.mutate()}>
        {disabled ? "Já há uma execução" : run.isPending ? "Enfileirando…" : "Enfileirar execução"}
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
  const [enabled, setEnabled] = useState(origin.enabled);
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
        enabled,
        config: configValues(configFields, config),
        options: optionValues(optionFields, options),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });

  return (
    <div className="grid gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        Origem ativa (uma origem pausada não lista, não agenda e não aceita entrada manual)
      </label>

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

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md bg-black/[0.02] px-3 py-2 ring-1 ring-(--color-line)">
      <span className="text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">{label}</span>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
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

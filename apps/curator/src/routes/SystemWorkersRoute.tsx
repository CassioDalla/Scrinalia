import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  clearWorkerSettings,
  saveWorkerSettings,
  triggerWorkerRun,
  type WorkerRunRequest,
  type WorkerSettingsRequest,
  type WorkerStatus,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { Field } from "@/components/ui/Field";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDateTime } from "@/lib/format";
import {
  describeConfig,
  formatDuration,
  hasActiveRun,
  isActiveRun,
  optionsToText,
  parseOptions,
  RUN_STATUS_LABEL,
  RUN_STATUS_TONE,
  UNIT_LABEL,
} from "@/lib/system";

/**
 * The AI workers: what each one is, with which preset and model it runs, and what is in its queue.
 *
 * The screen is a catalogue, not a form: the row answers the operational question, and the two
 * writes (configure the default, run it once) are opened on the row that needs them. A worker with a
 * run in flight disables both, because the API would refuse a second one anyway — the guarantee is
 * the partial unique index, and the screen only avoids offering what the database will reject.
 */
export function SystemWorkersRoute() {
  const { data, isPending, error } = useQuery({
    ...queries.systemWorkers(),
    // Poll only while something is running. The counts are not free — the transfer's counter
    // validates the whole staging table — so an idle panel keeps what it read.
    refetchInterval: (query) => (hasActiveRun(query.state.data?.workers) ? 5_000 : false),
  });

  return (
    <>
      <PageHeader screen="workers" />
      <PageBody className="gap-3">
        {error ? <ErrorState error={error} /> : null}

        {isPending ? (
          <div className="grid gap-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-24" />
            ))}
          </div>
        ) : null}

        {(data?.workers ?? []).map((worker) => <WorkerCard key={worker.name} worker={worker} />)}
      </PageBody>
    </>
  );
}

function WorkerCard({ worker }: { worker: WorkerStatus }) {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"none" | "run" | "settings">("none");
  const [feedback, setFeedback] = useState<string | null>(null);

  const active = isActiveRun(worker.active_run);

  const openPanel = (next: "run" | "settings") => {
    setFeedback(null);
    setPanel((current) => (current === next ? "none" : next));
    setOpen(true);
  };

  return (
    <Disclosure
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setPanel("none");
      }}
      toggleLabel="Ver detalhes, configurar e rodar"
      className={active ? "ring-(--color-accent)/40" : undefined}
      header={<WorkerHeader worker={worker} />}
      actions={
        <>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => openPanel("settings")}
            disabled={active}
            title={active ? "Há uma execução em andamento" : "Definir o padrão deste worker"}
          >
            Configurar
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={() => openPanel("run")}
            disabled={active}
            title={active ? "Há uma execução em andamento" : "Rodar agora com a configuração efetiva"}
          >
            {active ? "Em execução…" : ACTION.run.label}
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Fact label="Configuração efetiva">
            <span className="font-mono text-xs">{worker.settings.engine_name ?? "sem modelo"}</span>
            {worker.settings.preset ? <span className="text-(--color-muted)"> · {worker.settings.preset}</span> : null}
            <p className="mt-1 text-xs text-(--color-muted)">{describeConfig(worker.settings.config)}</p>
            {worker.settings.overridden ? (
              <Badge tone="accent" className="mt-1">
                padrão alterado
              </Badge>
            ) : (
              <Badge tone="neutral" className="mt-1">
                padrão do código
              </Badge>
            )}
          </Fact>

          <Fact label={`Fila (${UNIT_LABEL[worker.unit]})`}>
            {worker.pending == null ? (
              <span className="text-sm text-(--color-warn)">não mensurável</span>
            ) : (
              <span className="text-2xl leading-none font-semibold tabular-nums">
                {formatCount(worker.pending)}
              </span>
            )}
            <p className="mt-1 text-xs text-(--color-muted)">
              {formatCount(worker.processed ?? 0)} já processados
              {worker.failed ? ` · ${formatCount(worker.failed)} com falha` : ""}
            </p>
          </Fact>

          <Fact label="Última execução">
            {worker.last_run ? (
              <>
                <Badge tone={RUN_STATUS_TONE[worker.last_run.status]}>{RUN_STATUS_LABEL[worker.last_run.status]}</Badge>
                <p className="mt-1 text-xs text-(--color-muted)">
                  {formatDateTime(worker.last_run.queued_at)} · {formatDuration(worker.last_run.duration_ms)} ·{" "}
                  {worker.last_run.trigger === "API" ? "painel" : "linha de comando"}
                </p>
                {worker.last_run.error ? (
                  <p className="mt-1 text-xs text-(--color-danger)">{worker.last_run.error}</p>
                ) : null}
              </>
            ) : (
              <span className="text-sm text-(--color-muted)">nunca rodou</span>
            )}
          </Fact>
        </div>

        {worker.pending_reason ? (
          <Notice tone="warn">
            {worker.pending_reason}
          </Notice>
        ) : null}

        {worker.settings.note ? (
          <p className="text-xs text-(--color-muted)">{worker.settings.note}</p>
        ) : null}

        {!worker.governed ? (
          <p className="text-xs text-(--color-muted)">
            Este worker não respeita o bloqueio de revisão humana — é uma exceção documentada, não um descuido.
          </p>
        ) : null}

        {feedback ? (
          <Notice tone="ok">
            {feedback}
          </Notice>
        ) : null}

        {panel === "run" ? <RunPanel worker={worker} onDone={setFeedback} /> : null}
        {panel === "settings" ? <SettingsPanel worker={worker} onDone={setFeedback} /> : null}
      </div>
    </Disclosure>
  );
}

function WorkerHeader({ worker }: { worker: WorkerStatus }) {
  const active = isActiveRun(worker.active_run);
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="grid size-6 shrink-0 place-items-center rounded bg-black/5 text-xs font-semibold tabular-nums">
        {worker.order}
      </span>
      <span className="text-sm font-medium">{worker.label}</span>
      <span className="font-mono text-[11px] text-(--color-muted)">{worker.name}</span>
      {worker.settings.overridden ? <Badge tone="accent">padrão alterado</Badge> : null}
      {active ? <Badge tone="accent">{RUN_STATUS_LABEL[worker.active_run!.status]}</Badge> : null}
      {worker.pending != null && worker.pending > 0 ? (
        <Badge tone="warn">{formatCount(worker.pending)} na fila</Badge>
      ) : null}
      {/*
        The engine, the preset and the model stay on the collapsed row: "with which model is this
        running?" is the question the screen exists to answer, and making it require a click would
        hide the answer behind the very interaction it is meant to avoid.
      */}
      <span className="w-full font-mono text-[11px] text-(--color-muted)">
        {worker.settings.engine_name ?? "sem modelo"}
        {worker.settings.preset ? ` · ${worker.settings.preset}` : ""}
        {worker.settings.engine_name ? ` — ${describeConfig(worker.settings.config)}` : ""}
      </span>
      <span className="w-full text-xs text-(--color-muted)">{worker.description}</span>
    </span>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md bg-black/[0.02] px-3 py-2 ring-1 ring-(--color-line)">
      <p className="mb-1 text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">{label}</p>
      {children}
    </div>
  );
}

/** The per-run overrides. Nothing here is persisted; the defaults are the settings panel. */
function RunPanel({ worker, onDone }: { worker: WorkerStatus; onDone: (message: string) => void }) {
  const queryClient = useQueryClient();
  const settings = worker.settings;
  const [engine, setEngine] = useState(settings.engine_name ?? "");
  const [preset, setPreset] = useState(settings.preset ?? "");
  const [batch, setBatch] = useState(settings.db_batch_size ? String(settings.db_batch_size) : "");
  const [optionsText, setOptionsText] = useState(optionsToText(settings.options));

  const presets = (settings.available_engines ?? []).find((item) => item.name === engine)?.presets ?? [];

  const run = useMutation({
    mutationFn: () => {
      const parsed = parseOptions(optionsText);
      if (parsed.error) throw new Error(parsed.error);
      const body: WorkerRunRequest = {
        db_batch_size: batch ? Number(batch) : null,
        options: parsed.options ?? {},
      };
      if (settings.engine_source === "signature") {
        body.engine_name = engine || null;
        body.preset = preset || null;
      }
      return triggerWorkerRun(worker.name, body);
    },
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["system"] });
      onDone(`Execução #${created.run_id} aceita; acompanhe na aba Execuções.`);
    },
  });

  return (
    <Card className="bg-black/[0.02]">
      <CardBody className="grid gap-3">
        <p className="text-xs text-(--color-muted)">
          Esta execução usa a configuração efetiva acima, ajustada só para esta vez. Nada aqui vira padrão.
        </p>

        {settings.engine_source === "signature" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs">
              Engine
              <Select
                value={engine}
                onChange={(event) => {
                  setEngine(event.target.value);
                  setPreset("");
                }}
              >
                {(settings.available_engines ?? []).map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              Preset
              <Select value={preset} onChange={(event) => setPreset(event.target.value)}>
                <option value="">(o do código)</option>
                {presets.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name} — {describeConfig(item.config)}
                  </option>
                ))}
              </Select>
            </label>
          </div>
        ) : (
          <p className="text-xs text-(--color-muted)">
            {settings.engine_source === "llm_check_rule"
              ? "A engine e o preset deste worker vivem na regra LLM_CHECK ativa; aqui só os parâmetros da execução."
              : "Este worker não carrega modelo."}
          </p>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs">
            Tamanho do lote (vazio = o do código)
            <Input
              type="number"
              min={1}
              value={batch}
              onChange={(event) => setBatch(event.target.value)}
              placeholder={String(settings.db_batch_size ?? "")}
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs">
          Opções (JSON; ex.: {"{\"force\": true}"})
          <Textarea
            rows={2}
            value={optionsText}
            onChange={(event) => setOptionsText(event.target.value)}
            placeholder="{}"
          />
        </label>

        {run.error ? <ErrorState error={run.error} /> : null}

        <div className="flex items-center gap-2">
          <Button variant="primary" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? "Enviando…" : ACTION.run.label}
          </Button>
          <span className="text-xs text-(--color-muted)">
            {worker.pending == null
              ? "A fila não é mensurável a cada leitura."
              : `${formatCount(worker.pending)} ${UNIT_LABEL[worker.unit]} na fila.`}
          </span>
        </div>
      </CardBody>
    </Card>
  );
}

/** The persisted default of one worker, with its audit trail. */
function SettingsPanel({ worker, onDone }: { worker: WorkerStatus; onDone: (message: string) => void }) {
  const queryClient = useQueryClient();
  const settings = worker.settings;
  const [engine, setEngine] = useState(settings.engine_name ?? "");
  const [preset, setPreset] = useState(settings.preset ?? "");
  const [batch, setBatch] = useState(settings.db_batch_size ? String(settings.db_batch_size) : "");
  const [optionsText, setOptionsText] = useState(optionsToText(settings.options));

  const revisions = useQuery(queries.systemSettingsRevisions(worker.name));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["system"] });
  };

  const save = useMutation({
    mutationFn: () => {
      const parsed = parseOptions(optionsText);
      if (parsed.error) throw new Error(parsed.error);
      const body: WorkerSettingsRequest = {
        db_batch_size: batch ? Number(batch) : null,
        options: parsed.options ?? {},
      };
      if (settings.engine_source === "signature") {
        body.engine_name = engine || null;
        body.preset = preset || null;
      }
      return saveWorkerSettings(worker.name, body);
    },
    onSuccess: () => {
      invalidate();
      onDone("Padrão salvo; a próxima execução usa esta configuração.");
    },
  });

  const clear = useMutation({
    mutationFn: () => clearWorkerSettings(worker.name),
    onSuccess: () => {
      invalidate();
      onDone("Padrão removido; o worker voltou a seguir o código.");
    },
  });

  return (
    <Card className="bg-black/[0.02]">
      <CardBody className="grid gap-3">
        <p className="text-xs text-(--color-muted)">
          O padrão vale para toda execução deste worker, pela linha de comando ou pelo painel, até ser removido.
          Deixar um campo vazio mantém o valor do código.
        </p>

        {settings.engine_source === "signature" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs">
              Engine
              <Select
                value={engine}
                onChange={(event) => {
                  setEngine(event.target.value);
                  setPreset("");
                }}
              >
                <option value="">(a do código)</option>
                {(settings.available_engines ?? []).map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              Preset
              <Select value={preset} onChange={(event) => setPreset(event.target.value)}>
                <option value="">(o do código)</option>
                {((settings.available_engines ?? []).find((item) => item.name === engine)?.presets ?? []).map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name} — {describeConfig(item.config)}
                    </option>
                  ))}
              </Select>
            </label>
          </div>
        ) : (
          <p className="text-xs text-(--color-muted)">
            {settings.engine_source === "llm_check_rule"
              ? "A engine e o preset deste worker vivem na regra LLM_CHECK ativa (tela de regras de limpeza)."
              : "Este worker não carrega modelo; só os parâmetros abaixo são configuráveis."}
          </p>
        )}

        {/*
          One field, and it used to be two: the other was a label for a "who is changing this" input
          that no longer exists — the API takes the actor from the session since ADR 0009 — so the
          card showed a field title with nothing under it.
        */}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Tamanho do lote (vazio = o do código)">
            <Input
              type="number"
              min={1}
              value={batch}
              onChange={(event) => setBatch(event.target.value)}
              placeholder={String(settings.db_batch_size ?? "")}
            />
          </Field>
        </div>

        <label className="flex flex-col gap-1 text-xs">
          Opções (JSON; ex.: {"{\"force\": true}"})
          <Textarea rows={2} value={optionsText} onChange={(event) => setOptionsText(event.target.value)} placeholder="{}" />
        </label>

        {save.error ? <ErrorState error={save.error} /> : null}
        {clear.error ? <ErrorState error={clear.error} /> : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {ACTION.save.label} padrão
          </Button>
          <Button
            variant="secondary"
            onClick={() => clear.mutate()}
            disabled={!settings.overridden || clear.isPending}
            title={settings.overridden ? "Remover o padrão salvo" : "Não há padrão salvo"}
          >
            Voltar ao padrão do código
          </Button>
          {settings.updated_at ? (
            <span className="text-xs text-(--color-muted)">
              alterado em {formatDateTime(settings.updated_at)}
              {settings.updated_by ? ` por ${settings.updated_by}` : ""}
            </span>
          ) : null}
        </div>

        {revisions.data && (revisions.data.items ?? []).length > 0 ? (
          <div className="grid gap-1 border-t border-(--color-line) pt-2">
            <p className="text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">
              Histórico de alterações
            </p>
            {(revisions.data.items ?? []).map((revision) => (
              <p key={revision.revision_id} className="text-xs text-(--color-muted)">
                {formatDateTime(revision.changed_at)}
                {revision.changed_by ? ` · ${revision.changed_by}` : ""} ·{" "}
                {revision.after
                  ? `padrão definido (${describeSettings(revision.after)})`
                  : "padrão removido"}
              </p>
            ))}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function describeSettings(snapshot: Record<string, unknown>): string {
  const parts: string[] = [];
  if (snapshot.engine_name) parts.push(String(snapshot.engine_name));
  if (snapshot.preset) parts.push(String(snapshot.preset));
  if (snapshot.db_batch_size) parts.push(`lote ${String(snapshot.db_batch_size)}`);
  const options = snapshot.options as Record<string, unknown> | undefined;
  if (options && Object.keys(options).length > 0) parts.push(JSON.stringify(options));
  return parts.length > 0 ? parts.join(" · ") : "sem campos";
}

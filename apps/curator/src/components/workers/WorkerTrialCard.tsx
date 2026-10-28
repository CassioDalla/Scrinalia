import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import {
  previewWorkerQueue,
  saveWorkerSettings,
  triggerWorkerRun,
  triggerWorkerTrial,
  type WorkerRunDetail,
  type WorkerRunRequest,
  type WorkerSettings,
  type WorkerSettingsItem,
  type WorkerSettingsRequest,
  type WorkerTrialConfig,
  type WorkerTrialRequest,
  type WorkerTrialResult,
} from "@/api/client";
import { queries } from "@/api/queries";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { WorkerOptionsFields, initialOptionValues } from "@/components/workers/WorkerOptionsFields";
import { ACTION } from "@/lib/copy";
import { formatCount } from "@/lib/format";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE, describeOptions, formatDuration, isActiveRun } from "@/lib/system";

/**
 * Compare configurations on a sample before committing the collection to one of them (#71).
 *
 * The preview route prices a configuration; this card answers the other half — *is it any good?* The
 * trial runs the model over a fixed sample and writes no archival content (ADR 0018), so trying two
 * presets costs a comparison instead of a re-stamped collection.
 *
 * Three things the screen must not do: call the trial a production run (the ledger shows it with an
 * `ensaio` badge and the panel's "last run" ignores it), decide for the archivist (the table shows
 * the numbers and "Usar esta" is a click the person takes), or invent the pending count after the
 * save (it is the preview of the body that was just written, read after the write).
 */
export function WorkerTrialCard({
  worker,
  onSaved,
}: {
  worker: WorkerSettingsItem;
  onSaved: (message: string) => void;
}) {
  const settings = worker.settings;
  const queryClient = useQueryClient();
  const [sample, setSample] = useState("50");
  const [configs, setConfigs] = useState<WorkerSettingsRequest[]>(() => [
    draftFrom(settings),
    draftFrom(settings),
  ]);
  const [runId, setRunId] = useState<number | null>(null);
  const [savedBody, setSavedBody] = useState<WorkerSettingsRequest | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // The card's first paint after a reload: the last trial of this worker, if there is one. The list
  // read finds the row; the detail carries the result. A new trial replaces it with the queued row.
  const latest = useQuery(queries.latestTrial(worker.name));
  const latestId = latest.data?.items?.[0]?.run_id ?? null;
  const activeId = runId ?? latestId;
  const run = useQuery(queries.systemRun(activeId));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["system"] });
  };

  const sampleValue = Number(sample);
  const sampleValid = Number.isInteger(sampleValue) && sampleValue >= 5 && sampleValue <= 500;

  const trial = useMutation({
    mutationFn: (body: WorkerTrialRequest) => triggerWorkerTrial(worker.name, body),
    onSuccess: (created) => {
      setRunId(created.run_id);
      setSavedBody(null);
      setNotice(null);
      invalidate();
    },
  });

  // The number "run the whole collection" promises has to be the queue of the body that was just
  // saved, and it is read after the write, with the same resolution the run will use.
  const preview = useMutation({
    mutationFn: (body: WorkerSettingsRequest) => previewWorkerQueue(worker.name, body),
    onSuccess: () => setNotice(null),
  });

  const choose = useMutation({
    mutationFn: (config: WorkerTrialConfig) => saveWorkerSettings(worker.name, config.settings),
    onSuccess: (_saved, config) => {
      setSavedBody(config.settings);
      // A pending count from the previously chosen configuration would be a number about another
      // body under the button that promises this one.
      preview.reset();
      setNotice("Padrão salvo a partir do ensaio; a próxima execução usa esta configuração.");
      invalidate();
      onSaved("Padrão salvo a partir do ensaio.");
    },
  });

  const runAll = useMutation({
    mutationFn: () => triggerWorkerRun(worker.name, {}),
    onSuccess: (created) => {
      setNotice(
        `Execução #${created.run_id} enfileirada com o padrão salvo; acompanhe em Execuções.`,
      );
      invalidate();
    },
  });

  const busy = run.data !== undefined && isActiveRun(run.data);
  const body: WorkerTrialRequest = {
    sample: sampleValid ? sampleValue : 50,
    configs: configs.map(toRunRequest),
  };

  return (
    <div className="grid gap-3 rounded-lg bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">Comparar configurações</span>
        <span className="text-xs text-(--color-muted)">o ensaio não altera o acervo</span>
      </div>

      <p className="text-xs text-(--color-muted)">
        O ensaio aplica cada configuração à mesma amostra e mostra a concordância com as correções
        humanas de tipologia. Ele ocupa a vaga desta etapa como uma execução; a escolha só vira padrão
        quando você clicar em <strong>Salvar como padrão</strong>.
      </p>

      <div className="grid gap-3 lg:grid-cols-2">
        {configs.map((config, index) => (
          <ConfigEditor
            key={index}
            title={`Configuração ${index === 0 ? "A" : "B"}`}
            settings={settings}
            config={config}
            onChange={(next) =>
              setConfigs((current) => current.map((item, position) => (position === index ? next : item)))
            }
          />
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Descrições na Amostra (5 a 500)" hint="As correções humanas são lidas até o mesmo limite.">
          <Input
            type="number"
            min={5}
            max={500}
            value={sample}
            onChange={(event) => setSample(event.target.value)}
            className="w-32"
          />
        </Field>
        <Button
          variant="primary"
          onClick={() => trial.mutate(body)}
          disabled={trial.isPending || busy || !sampleValid}
          title={busy ? "Já há um ensaio ou uma execução desta etapa em andamento." : undefined}
        >
          {trial.isPending ? "Enfileirando…" : "Enfileirar ensaio"}
        </Button>
        {!sampleValid ? <span className="text-xs text-(--color-danger)">A amostra vai de 5 a 500.</span> : null}
      </div>

      {trial.error ? <ErrorState error={trial.error} /> : null}
      {choose.error ? <ErrorState error={choose.error} /> : null}
      {preview.error ? <ErrorState error={preview.error} /> : null}
      {runAll.error ? <ErrorState error={runAll.error} /> : null}
      {notice ? <Notice tone="ok">{notice}</Notice> : null}

      {latest.isPending && runId === null ? <Skeleton className="h-16" /> : null}
      {run.data ? <TrialRunPanel run={run.data} /> : null}

      {run.data?.trial_result ? (
        <TrialComparison
          result={run.data.trial_result}
          onUse={(config) => choose.mutate(config)}
          using={choose.isPending}
        />
      ) : null}

      {run.data?.trial_result ? (
        <div className="grid gap-2 border-t border-(--color-line) pt-3">
          <p className="text-xs font-semibold tracking-wide text-(--color-muted) uppercase">
            Rodar no acervo inteiro
          </p>
          <p className="text-xs text-(--color-muted)">
            {savedBody
              ? "Primeiro confira a fila do padrão que acabou de ser salvo; o número é o que a execução vai ler."
              : "Escolha uma configuração acima para salvá-la como padrão."}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => savedBody && preview.mutate(savedBody)}
              disabled={!savedBody || preview.isPending}
            >
              {preview.isPending ? ACTION.preview.pending : ACTION.preview.label}
            </Button>
            <Button
              variant="primary"
              onClick={() => runAll.mutate()}
              disabled={!savedBody || preview.data === undefined || runAll.isPending || preview.data.pending === 0}
              title={
                preview.data?.pending === 0
                  ? "A fila está vazia com este padrão."
                  : "Enfileira a execução com o padrão salvo, sem ajustes só desta vez."
              }
            >
              {runAll.isPending ? "Enfileirando…" : "Enfileirar execução"}
            </Button>
            {preview.data ? (
              <span className="text-xs text-(--color-muted)">
                {preview.data.pending == null
                  ? (preview.data.pending_reason ?? "Não é possível contar a fila.")
                  : `${formatCount(preview.data.pending)} na fila com o padrão salvo.`}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The body the settings screen writes, starting from the effective configuration. */
function draftFrom(settings: WorkerSettings): WorkerSettingsRequest {
  return {
    engine_name: settings.engine_name,
    preset: settings.preset,
    db_batch_size: settings.db_batch_size,
    options: initialOptionValues(settings.options ?? {}, settings.declared_options ?? [], "settings"),
  };
}

/** One comparison body keeps the same shape a run uses, so the API validates it the same way. */
function toRunRequest(config: WorkerSettingsRequest): WorkerRunRequest {
  return {
    engine_name: config.engine_name,
    preset: config.preset,
    db_batch_size: config.db_batch_size,
    options: config.options,
  };
}

function ConfigEditor({
  title,
  settings,
  config,
  onChange,
}: {
  title: string;
  settings: WorkerSettings;
  config: WorkerSettingsRequest;
  onChange: (next: WorkerSettingsRequest) => void;
}) {
  const engines = settings.available_engines ?? [];
  const presets = engines.find((engine) => engine.name === config.engine_name)?.presets ?? [];

  return (
    <div className="grid gap-2 rounded-md bg-(--color-surface) p-3 ring-1 ring-(--color-line)">
      <span className="text-xs font-semibold tracking-wide text-(--color-muted) uppercase">{title}</span>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Motor">
          <Select
            value={config.engine_name ?? ""}
            onChange={(event) => onChange({ ...config, engine_name: event.target.value || null, preset: null })}
          >
            <option value="">(o padrão do sistema)</option>
            {engines.map((engine) => (
              <option key={engine.name} value={engine.name}>
                {engine.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Preset">
          <Select
            value={config.preset ?? ""}
            onChange={(event) => onChange({ ...config, preset: event.target.value || null })}
          >
            <option value="">(o padrão do sistema)</option>
            {presets.map((preset) => (
              <option key={preset.name} value={preset.name}>
                {preset.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Tamanho do Lote (vazio = o do sistema)">
        <Input
          type="number"
          min={1}
          value={config.db_batch_size ?? ""}
          onChange={(event) =>
            onChange({ ...config, db_batch_size: event.target.value ? Number(event.target.value) : null })
          }
        />
      </Field>
      <WorkerOptionsFields
        settings={settings}
        mode="settings"
        values={config.options ?? {}}
        onChange={(next) => onChange({ ...config, options: next })}
      />
    </div>
  );
}

/** The queued/running/failed trial: its state, and where to watch it. */
function TrialRunPanel({ run }: { run: WorkerRunDetail }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
      <Badge tone={RUN_STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</Badge>
      <span>
        Ensaio #{run.run_id} · {formatDuration(run.duration_ms)}
      </span>
      {isActiveRun(run) ? (
        <span>
          o resultado aparece quando a execução terminar; acompanhe em{" "}
          <Link to="/sistema/workers" search={{ aba: "execucoes" }} className="underline">
            Execuções
          </Link>
          .
        </span>
      ) : null}
      {run.status === "FAILED" && run.error ? (
        <span className="text-(--color-danger)">{run.error}</span>
      ) : null}
    </div>
  );
}

/** The side-by-side table. The archivist reads it and takes the decision; the button writes it. */
function TrialComparison({
  result,
  onUse,
  using,
}: {
  result: WorkerTrialResult;
  onUse: (config: WorkerTrialConfig) => void;
  using: boolean;
}) {
  const configs = result.configs ?? [];
  const verdictIds = result.sample.verdict_ids ?? [];
  const sampledIds = result.sample.description_ids ?? [];
  const unknown = result.unknown_verdicts ?? [];
  const scored = configs.filter((config) => config.agreement != null);
  const best = scored.length >= 2 ? Math.max(...scored.map((config) => config.agreement as number)) : null;

  return (
    <div className="grid gap-2">
      <p className="text-xs text-(--color-muted)">
        {result.sample.verdicts_available} veredito(s) humano(s) de tipologia no acervo ·{" "}
        {verdictIds.length} usado(s) neste ensaio · amostra aleatória de {sampledIds.length} descrição(ões).
        {result.sample.verdicts_available === 0 ? (
          <>
            {" "}
            A concordância ainda não pode ser medida: corrija uma recusa em{" "}
            <Link to="/arranjo/tipologias" className="underline">
              Tipologias
            </Link>{" "}
            para criar o primeiro veredito.
          </>
        ) : null}
      </p>

      {unknown.length > 0 ? (
        <Notice tone="warn">Vereditos fora do catálogo ativo (contam como erro): {unknown.join(", ")}.</Notice>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-(--color-muted)">
              <th className="py-1 pr-3 font-medium">Configuração</th>
              <th className="py-1 pr-3 font-medium">Concordância</th>
              <th className="py-1 pr-3 font-medium">Cobertura</th>
              <th className="py-1 pr-3 font-medium">Abstenção</th>
              <th className="py-1 pr-3 font-medium">Maior Rótulo</th>
              <th className="py-1 pr-3 font-medium">Entropia</th>
              <th className="py-1 pr-3 font-medium">s/descrição</th>
              <th className="py-1 pr-3 font-medium">Fila</th>
              <th className="py-1 pr-3 font-medium">Projeção</th>
              <th className="py-1 font-medium" />
            </tr>
          </thead>
          <tbody>
            {configs.map((config, index) => (
              <tr key={index} className="border-t border-(--color-line) align-top">
                <td className="py-2 pr-3">
                  <span className="font-mono text-[11px]">
                    {config.engine_name ?? "—"}
                    {config.preset ? ` · ${config.preset}` : ""}
                  </span>
                  <span className="block text-[11px] text-(--color-muted)">{describeOptions(config.options)}</span>
                  {best !== null && config.agreement === best ? <Badge tone="ok">melhor concordância</Badge> : null}
                </td>
                <td className="py-2 pr-3 tabular-nums">
                  {config.agreement == null ? "—" : `${(config.agreement * 100).toFixed(1)}%`}
                  <span className="text-(--color-muted)"> ({config.verdicts_scored})</span>
                </td>
                <td className="py-2 pr-3 tabular-nums">{(config.coverage * 100).toFixed(0)}%</td>
                <td className="py-2 pr-3 tabular-nums">{(config.abstention_rate * 100).toFixed(0)}%</td>
                <td className="py-2 pr-3">
                  {config.largest_share || "—"}{" "}
                  <span className="text-(--color-muted)">({(config.largest_share_value * 100).toFixed(0)}%)</span>
                </td>
                <td className="py-2 pr-3 tabular-nums">{config.entropy_bits.toFixed(2)}</td>
                <td className="py-2 pr-3 tabular-nums">{config.seconds_per_document.toFixed(2)}</td>
                <td className="py-2 pr-3 tabular-nums">
                  {config.pending == null ? (config.pending_reason ?? "—") : formatCount(config.pending)}
                </td>
                <td className="py-2 pr-3 tabular-nums">
                  {config.projected_hours == null ? "—" : `${config.projected_hours.toFixed(1)} h`}
                </td>
                <td className="py-2">
                  <Button size="sm" variant="secondary" onClick={() => onUse(config)} disabled={using}>
                    Salvar como padrão
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] text-(--color-muted)">
        Cobertura = vereditos em que a configuração deu um rótulo. A projeção usa a fila desta
        configuração no ritmo medido e não inclui o carregamento do modelo.
      </p>
    </div>
  );
}

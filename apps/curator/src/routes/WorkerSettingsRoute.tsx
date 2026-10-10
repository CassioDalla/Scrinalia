import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  clearWorkerSettings,
  saveWorkerSettings,
  type WorkerSettingsItem,
  type WorkerSettingsRequest,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { ACTION } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { describeConfig, optionsToText, parseOptions } from "@/lib/system";

/**
 * The persisted configuration of the AI workers: the default each one follows, and its history.
 *
 * The other half of `/sistema/workers`, split out in issue #53. The panel answers what the machine
 * is *doing* — the queue, the pending counter, a run in flight; this screen answers what the
 * installation is *set* to do — the row in `archive_worker_settings`, its revisions, and the
 * engine/preset choice. The split moved where the write is made, never what it means: the precedence
 * is still `explicit argument > the row > the signature default`, and a field left empty keeps
 * following the code.
 *
 * The read is `/system/workers/settings` and not `/system/workers`: the second one counts nine
 * queues, and this screen shows none of them.
 */
export function WorkerSettingsRoute() {
  const { data, isPending, error } = useQuery(queries.systemWorkerSettings());

  return (
    <>
      <PageHeader screen="workerSettings" />
      <PageBody className="gap-3">
        {error ? <ErrorState error={error} /> : null}

        {isPending ? (
          <div className="grid gap-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-20" />
            ))}
          </div>
        ) : null}

        {(data?.workers ?? []).map((worker) => (
          <WorkerSettingsCard key={worker.name} worker={worker} />
        ))}
      </PageBody>
    </>
  );
}

function WorkerSettingsCard({ worker }: { worker: WorkerSettingsItem }) {
  const [feedback, setFeedback] = useState<string | null>(null);

  return (
    <Disclosure
      // Closing the row clears the confirmation with it: a "padrão salvo" that stays on a collapsed
      // row would keep claiming a write the archivist can no longer see the form of.
      onOpenChange={(next) => {
        if (!next) setFeedback(null);
      }}
      toggleLabel="Configurar este worker"
      header={<SettingsHeader worker={worker} />}
    >
      <div className="grid gap-3">
        {feedback ? <Notice tone="ok">{feedback}</Notice> : null}
        <SettingsForm worker={worker} onDone={setFeedback} />
      </div>
    </Disclosure>
  );
}

/** The row the configuration screen exists to read: who it is, what it runs, and what was changed. */
function SettingsHeader({ worker }: { worker: WorkerSettingsItem }) {
  const settings = worker.settings;
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="grid size-6 shrink-0 place-items-center rounded bg-black/5 text-xs font-semibold tabular-nums">
        {worker.order}
      </span>
      <span className="text-sm font-medium">{worker.label}</span>
      <span className="font-mono text-[11px] text-(--color-muted)">{worker.name}</span>
      {settings.overridden ? (
        <Badge tone="accent">padrão alterado</Badge>
      ) : (
        <Badge tone="neutral">padrão do código</Badge>
      )}
      <span className="w-full font-mono text-[11px] text-(--color-muted)">
        {settings.engine_name ?? "sem modelo"}
        {settings.preset ? ` · ${settings.preset}` : ""}
        {settings.engine_name ? ` — ${describeConfig(settings.config)}` : ""}
      </span>
      <span className="w-full text-xs text-(--color-muted)">{worker.description}</span>
      {settings.updated_at ? (
        <span className="w-full text-xs text-(--color-muted)">
          alterado em {formatDateTime(settings.updated_at)}
          {settings.updated_by ? ` por ${settings.updated_by}` : ""}
        </span>
      ) : null}
    </span>
  );
}

/** The persisted default of one worker, with its audit trail. */
function SettingsForm({ worker, onDone }: { worker: WorkerSettingsItem; onDone: (message: string) => void }) {
  const queryClient = useQueryClient();
  const settings = worker.settings;
  const [engine, setEngine] = useState(settings.engine_name ?? "");
  const [preset, setPreset] = useState(settings.preset ?? "");
  const [batch, setBatch] = useState(settings.db_batch_size ? String(settings.db_batch_size) : "");
  const [optionsText, setOptionsText] = useState(optionsToText(settings.options));

  const revisions = useQuery(queries.systemSettingsRevisions(worker.name));

  const invalidate = () => {
    // Everything under `system` is invalidated on purpose: the panel on `/sistema/workers` reads the
    // same row as the effective configuration, and a saved default that did not reach it would have
    // the two screens disagree about what the next run uses.
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
    <div className="grid gap-3">
      <p className="text-xs text-(--color-muted)">
        O padrão vale para toda execução deste worker, pela linha de comando ou pelo painel, até ser removido.
        Deixar um campo vazio mantém o valor do código.
      </p>

      {settings.engine_source === "signature" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Engine">
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
          </Field>
          <Field label="Preset">
            <Select value={preset} onChange={(event) => setPreset(event.target.value)}>
              <option value="">(o do código)</option>
              {((settings.available_engines ?? []).find((item) => item.name === engine)?.presets ?? []).map(
                (item) => (
                  <option key={item.name} value={item.name}>
                    {item.name} — {describeConfig(item.config)}
                  </option>
                ),
              )}
            </Select>
          </Field>
        </div>
      ) : (
        <p className="text-xs text-(--color-muted)">
          {settings.engine_source === "llm_check_rule"
            ? "A engine e o preset deste worker vivem na regra LLM_CHECK ativa (tela de regras de limpeza)."
            : "Este worker não carrega modelo; só os parâmetros abaixo são configuráveis."}
        </p>
      )}

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

      <Field
        label={
          <>
            Opções (JSON; ex.: <code>{'{"force": true}'}</code>)
          </>
        }
      >
        <Textarea rows={2} value={optionsText} onChange={(event) => setOptionsText(event.target.value)} placeholder="{}" />
      </Field>

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
      </div>

      {settings.note ? <p className="text-xs text-(--color-muted)">{settings.note}</p> : null}

      {revisions.data && (revisions.data.items ?? []).length > 0 ? (
        <div className="grid gap-1 border-t border-(--color-line) pt-2">
          <p className="text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">
            Histórico de alterações
          </p>
          {(revisions.data.items ?? []).map((revision) => (
            <p key={revision.revision_id} className="text-xs text-(--color-muted)">
              {formatDateTime(revision.changed_at)}
              {revision.changed_by ? ` · ${revision.changed_by}` : ""} ·{" "}
              {revision.after ? `padrão definido (${describeSettings(revision.after)})` : "padrão removido"}
            </p>
          ))}
        </div>
      ) : null}
    </div>
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

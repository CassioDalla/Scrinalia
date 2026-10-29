import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  clearWorkerSchedule,
  clearWorkerSettings,
  previewWorkerQueue,
  saveWorkerSchedule,
  saveWorkerSettings,
  type WorkerRunRequest,
  type WorkerSchedule,
  type WorkerScheduleRequest,
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
import { WorkerOptionsFields, initialOptionValues, optionsForRequest } from "@/components/workers/WorkerOptionsFields";
import { WorkerTrialCard } from "@/components/workers/WorkerTrialCard";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import type { Messages } from "@/i18n/pt";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDateTime } from "@/lib/format";
import { describeConfig, parseOptions } from "@/lib/system";

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
  const messages = useCopy();
  const [feedback, setFeedback] = useState<string | null>(null);

  return (
    <Disclosure
      // Closing the row clears the confirmation with it: a "padrão salvo" that stays on a collapsed
      // row would keep claiming a write the archivist can no longer see the form of.
      onOpenChange={(next) => {
        if (!next) setFeedback(null);
      }}
      toggleLabel={messages.pages.workerSettings.configure}
      header={<SettingsHeader worker={worker} />}
    >
      <div className="grid gap-3">
        {feedback ? <Notice tone="ok">{feedback}</Notice> : null}
        <SettingsForm worker={worker} onDone={setFeedback} />
        {worker.settings.trial_supported ? <WorkerTrialCard worker={worker} onSaved={setFeedback} /> : null}
        <ScheduleCard worker={worker} />
      </div>
    </Disclosure>
  );
}

/** The row the configuration screen exists to read: who it is, what it runs, and what was changed. */
function SettingsHeader({ worker }: { worker: WorkerSettingsItem }) {
  const messages = useCopy();
  const settings = worker.settings;
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="grid size-6 shrink-0 place-items-center rounded bg-black/5 text-xs font-semibold tabular-nums">
        {worker.order}
      </span>
      <span className="text-sm font-medium">{worker.label}</span>
      <span className="font-mono text-[11px] text-(--color-muted)">{worker.name}</span>
      {settings.overridden ? (
        <Badge tone="accent">{messages.pages.workerSettings.changedBadge}</Badge>
      ) : (
        <Badge tone="neutral">{messages.pages.workerSettings.codeBadge}</Badge>
      )}
      <span className="w-full font-mono text-[11px] text-(--color-muted)">
        {settings.engine_name ?? messages.system.noModel}
        {settings.preset ? ` · ${settings.preset}` : ""}
        {settings.engine_name ? ` — ${describeConfig(settings.config)}` : ""}
      </span>
      <span className="w-full text-xs text-(--color-muted)">{worker.description}</span>
      {settings.updated_at ? (
        <span className="w-full text-xs text-(--color-muted)">
          {settings.updated_by
            ? fill(messages.pages.workerSettings.changedBy, {
                date: formatDateTime(settings.updated_at),
                name: settings.updated_by,
              })
            : fill(messages.pages.workerSettings.changedAt, {
                date: formatDateTime(settings.updated_at),
              })}
        </span>
      ) : null}
    </span>
  );
}

/** The persisted default of one worker, with its audit trail. */
function SettingsForm({ worker, onDone }: { worker: WorkerSettingsItem; onDone: (message: string) => void }) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const settings = worker.settings;
  const [engine, setEngine] = useState(settings.engine_name ?? "");
  const [preset, setPreset] = useState(settings.preset ?? "");
  const [batch, setBatch] = useState(settings.db_batch_size ? String(settings.db_batch_size) : "");
  const [optionValues, setOptionValues] = useState<Record<string, unknown>>(
    initialOptionValues(settings.options ?? {}, settings.declared_options ?? [], "settings"),
  );

  const revisions = useQuery(queries.systemSettingsRevisions(worker.name));

  const invalidate = () => {
    // Everything under `system` is invalidated on purpose: the panel on `/sistema/workers` reads the
    // same row as the effective configuration, and a saved default that did not reach it would have
    // the two screens disagree about what the next run uses.
    void queryClient.invalidateQueries({ queryKey: ["system"] });
  };

  /**
   * The configuration the form is proposing, built once for the preview and for the save.
   *
   * Two builders would be two answers to "what would this screen save?", and the preview exists
   * precisely to answer it before the write.
   */
  const buildBody = (): WorkerSettingsRequest => {
    const body: WorkerSettingsRequest = {
      db_batch_size: batch ? Number(batch) : null,
      options: optionsForRequest(optionValues, settings.declared_options ?? [], "settings"),
    };
    if (settings.engine_source === "signature") {
      body.engine_name = engine || null;
      body.preset = preset || null;
    }
    return body;
  };

  const save = useMutation({
    mutationFn: () => saveWorkerSettings(worker.name, buildBody()),
    onSuccess: () => {
      invalidate();
      onDone(messages.pages.workerSettings.saved);
    },
  });

  /**
   * The queue of the proposed configuration, cleared as soon as a field moves.
   *
   * A number that stayed on screen after the threshold changed would be a measurement of something
   * else under the label of what the form now says.
   */
  const preview = useMutation({
    mutationFn: () => previewWorkerQueue(worker.name, buildBody()),
  });
  const clearPreview = () => preview.reset();

  const clear = useMutation({
    mutationFn: () => clearWorkerSettings(worker.name),
    onSuccess: () => {
      invalidate();
      onDone(messages.pages.workerSettings.cleared);
    },
  });

  return (
    <div className="grid gap-3">
      <p className="text-xs text-(--color-muted)">{messages.pages.workerSettings.intro}</p>

      {settings.engine_source === "signature" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={messages.pages.workerSettings.engineField}>
            <Select
              value={engine}
              onChange={(event) => {
                setEngine(event.target.value);
                setPreset("");
                clearPreview();
              }}
            >
              <option value="">{messages.pages.workerSettings.codeOption}</option>
              {(settings.available_engines ?? []).map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={messages.pages.workerSettings.presetField}>
            <Select
              value={preset}
              onChange={(event) => {
                setPreset(event.target.value);
                clearPreview();
              }}
            >
              <option value="">{messages.pages.workerSettings.codeOption}</option>
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
            ? messages.pages.workerSettings.engineFromRule
            : messages.pages.workerSettings.noModel}
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={messages.pages.workerSettings.batchField}>
          <Input
            type="number"
            min={1}
            value={batch}
            onChange={(event) => {
              setBatch(event.target.value);
              clearPreview();
            }}
            placeholder={String(settings.db_batch_size ?? "")}
          />
        </Field>
      </div>

      <WorkerOptionsFields
        settings={settings}
        mode="settings"
        values={optionValues}
        onChange={(next) => {
          setOptionValues(next);
          clearPreview();
        }}
      />

      {save.error ? <ErrorState error={save.error} /> : null}
      {clear.error ? <ErrorState error={clear.error} /> : null}
      {preview.error ? <ErrorState error={preview.error} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
          {messages.pages.workerSettings.saveAsDefault}
        </Button>
        <Button
          variant="secondary"
          onClick={() => preview.mutate()}
          disabled={preview.isPending}
          title={messages.pages.workerSettings.previewTitle}
        >
          {preview.isPending ? ACTION.preview.pending : ACTION.preview.label}
        </Button>
        <Button
          variant="secondary"
          onClick={() => clear.mutate()}
          disabled={!settings.overridden || clear.isPending}
          title={
            settings.overridden
              ? messages.pages.workerSettings.clearTitle
              : messages.pages.workerSettings.noDefaultTitle
          }
        >
          {messages.pages.workerSettings.backToCode}
        </Button>
      </div>

      {preview.data ? (
        <p className="text-xs text-(--color-muted)">
          {preview.data.pending == null
            ? (preview.data.pending_reason ?? messages.pages.workerSettings.queueUnknown)
            : fill(messages.pages.workerSettings.queueCount, {
                count: formatCount(preview.data.pending),
              })}
        </p>
      ) : null}

      {settings.note ? <p className="text-xs text-(--color-muted)">{settings.note}</p> : null}

      {revisions.data && (revisions.data.items ?? []).length > 0 ? (
        <div className="grid gap-1 border-t border-(--color-line) pt-2">
          <p className="text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">
            {messages.pages.workerSettings.revisionsTitle}
          </p>
          {(revisions.data.items ?? []).map((revision) => (
            <p key={revision.revision_id} className="text-xs text-(--color-muted)">
              {formatDateTime(revision.changed_at)}
              {revision.changed_by ? ` · ${revision.changed_by}` : ""} ·{" "}
              {revision.after
                ? fill(messages.pages.workerSettings.defaultSet, {
                    settings: describeSettings(revision.after, messages),
                  })
                : messages.pages.workerSettings.defaultRemoved}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ScheduleCard({ worker }: { worker: WorkerSettingsItem }) {
  const schedule = useQuery(queries.systemSchedule(worker.name));

  if (schedule.isPending) return <Skeleton className="h-24" />;
  if (schedule.error) return <ErrorState error={schedule.error} />;
  return <ScheduleForm worker={worker} schedule={schedule.data ?? null} />;
}

/**
 * The worker's agenda: the cron, the zone and the request each scheduled run uses.
 *
 * The request is pinned, which is why the form starts from the schedule's body and not from the
 * settings: the parts the operator did not name fall back to the settings at enqueue time, and the
 * ones named here stay. A paused agenda stores no next run, so the form shows "pausada" instead of a
 * date it would have to invent.
 */
function ScheduleForm({ worker, schedule }: { worker: WorkerSettingsItem; schedule: WorkerSchedule | null }) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const settings = worker.settings;
  const [feedback, setFeedback] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(schedule?.enabled ?? false);
  const [cron, setCron] = useState(schedule?.cron ?? "");
  const [timezone, setTimezone] = useState(
    schedule?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
  );
  const [engine, setEngine] = useState(schedule?.request.engine_name ?? "");
  const [preset, setPreset] = useState(schedule?.request.preset ?? "");
  const [batch, setBatch] = useState(
    schedule?.request.db_batch_size ? String(schedule.request.db_batch_size) : "",
  );
  const [optionValues, setOptionValues] = useState<Record<string, unknown>>(
    initialOptionValues(schedule?.request.options ?? {}, settings.declared_options ?? [], "run"),
  );
  const [engineText, setEngineText] = useState(
    schedule && Object.keys(schedule.request.engine_options ?? {}).length > 0
      ? JSON.stringify(schedule.request.engine_options)
      : "",
  );

  const parsed = parseOptions(engineText);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["system"] });
  };

  const buildBody = (): WorkerScheduleRequest => {
    const request: WorkerRunRequest = {
      engine_name: settings.engine_source === "signature" ? engine || null : null,
      preset: settings.engine_source === "signature" ? preset || null : null,
      db_batch_size: batch ? Number(batch) : null,
      options: optionsForRequest(optionValues, settings.declared_options ?? [], "run"),
      engine_options: parsed.options ?? {},
    };
    return { enabled, cron, timezone: timezone.trim() || null, request };
  };

  const save = useMutation({
    mutationFn: () => saveWorkerSchedule(worker.name, buildBody()),
    onSuccess: (saved) => {
      invalidate();
      setFeedback(
        saved.enabled
          ? fill(messages.pages.workerSettings.scheduleSaved, { date: formatDateTime(saved.next_run_at) })
          : messages.pages.workerSettings.schedulePausedNotice,
      );
    },
  });

  const clear = useMutation({
    mutationFn: () => clearWorkerSchedule(worker.name),
    onSuccess: () => {
      invalidate();
      setEnabled(false);
      setCron("");
      setFeedback(messages.pages.workerSettings.scheduleRemoved);
    },
  });

  return (
    <div className="grid gap-3 rounded-lg bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">{messages.pages.workerSettings.schedule}</span>
        <span className="text-xs text-(--color-muted)">
          {schedule
            ? schedule.enabled
              ? fill(messages.pages.workerSettings.nextRun, { date: formatDateTime(schedule.next_run_at) })
              : messages.pages.workerSettings.paused
            : messages.pages.workerSettings.noSchedule}
        </span>
      </div>

      <p className="text-xs text-(--color-muted)">{messages.pages.workerSettings.scheduleIntro}</p>

      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={messages.pages.workerSettings.stateField}>
          <Select value={enabled ? "on" : "off"} onChange={(event) => setEnabled(event.target.value === "on")}>
            <option value="on">{messages.pages.workerSettings.active}</option>
            <option value="off">{messages.pages.workerSettings.paused}</option>
          </Select>
        </Field>
        <Field label={messages.pages.workerSettings.cronField}>
          <Input value={cron} onChange={(event) => setCron(event.target.value)} placeholder="0 2 * * *" />
        </Field>
        <Field label={messages.pages.workerSettings.timezoneField}>
          <Input
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="America/Sao_Paulo"
          />
        </Field>
      </div>

      {settings.engine_source === "signature" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={messages.pages.workerSettings.enginePinField}>
            <Select
              value={engine}
              onChange={(event) => {
                setEngine(event.target.value);
                setPreset("");
              }}
            >
              <option value="">{messages.pages.workerSettings.savedOption}</option>
              {(settings.available_engines ?? []).map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={messages.pages.workerSettings.presetField}>
            <Select value={preset} onChange={(event) => setPreset(event.target.value)}>
              <option value="">{messages.pages.workerSettings.savedOption}</option>
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
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={messages.pages.workerSettings.batchFieldShort}>
          <Input
            value={batch}
            onChange={(event) => setBatch(event.target.value)}
            placeholder={messages.pages.workerSettings.savedOption}
          />
        </Field>
        <Field label={messages.pages.workerSettings.engineOptionsField}>
          <Textarea
            rows={2}
            value={engineText}
            onChange={(event) => setEngineText(event.target.value)}
            placeholder="{}"
          />
        </Field>
      </div>

      <WorkerOptionsFields settings={settings} mode="run" values={optionValues} onChange={setOptionValues} />

      {parsed.error ? <Notice tone="warn">{parsed.error}</Notice> : null}
      {save.error ? <ErrorState error={save.error} /> : null}
      {feedback ? <Notice tone="ok">{feedback}</Notice> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          onClick={() => save.mutate()}
          disabled={save.isPending || parsed.error !== undefined}
        >
          {save.isPending ? ACTION.save.pending : ACTION.save.label}
        </Button>
        {schedule ? (
          <Button variant="secondary" onClick={() => clear.mutate()} disabled={clear.isPending}>
            {clear.isPending ? ACTION.remove.pending : ACTION.remove.label}
          </Button>
        ) : null}
        <span className="text-xs text-(--color-muted)">
          {schedule
            ? fill(messages.pages.workerSettings.updatedBy, { name: schedule.updated_by ?? "—" })
            : messages.pages.workerSettings.noSchedule}
        </span>
      </div>
    </div>
  );
}

function describeSettings(snapshot: Record<string, unknown>, messages: Messages): string {
  const parts: string[] = [];
  if (snapshot.engine_name) parts.push(String(snapshot.engine_name));
  if (snapshot.preset) parts.push(String(snapshot.preset));
  if (snapshot.db_batch_size) {
    parts.push(fill(messages.pages.workerSettings.snapshotBatch, { size: String(snapshot.db_batch_size) }));
  }
  const options = snapshot.options as Record<string, unknown> | undefined;
  if (options && Object.keys(options).length > 0) parts.push(JSON.stringify(options));
  return parts.length > 0 ? parts.join(" · ") : messages.pages.workerSettings.snapshotEmpty;
}

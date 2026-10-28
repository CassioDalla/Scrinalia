import type { FailureSource, WorkerRun, WorkerRunStatus, WorkerStatus } from "@/api/client";
import { activeMessages } from "@/i18n/locale";

/**
 * Human labels for the run lifecycle.
 *
 * The API speaks the enum; the operator reads Portuguese. Same rule as ``REVIEW_STATUS_LABEL``:
 * the mapping lives in the screen, which is what lets the contract stay in English.
 */
export const RUN_STATUS_LABEL = new Proxy({} as Record<WorkerRunStatus, string>, {
  get(_target, key) {
    return activeMessages().system.runStatus[key as WorkerRunStatus];
  },
});

export const RUN_STATUS_TONE: Record<
  WorkerRunStatus,
  "neutral" | "ok" | "warn" | "danger" | "accent"
> = {
  QUEUED: "neutral",
  RUNNING: "accent",
  SUCCESS: "ok",
  FAILED: "danger",
  INTERRUPTED: "warn",
  // A cancellation is a deliberate verdict, not an accident: neutral, where the interrupted run
  // (the runner disappeared) keeps the warning tone. The label says which one it was.
  CANCELLED: "neutral",
};

/**
 * Where a failure was seen, in the operator's words.
 *
 * A group can carry both: the same root cause may have broken a worker execution and an HTTP
 * request, and that is one line on the failures panel, not two.
 */
export const FAILURE_SOURCE_LABEL = new Proxy({} as Record<FailureSource, string>, {
  get(_target, key) {
    return activeMessages().system.failureSource[key as FailureSource];
  },
});

/** Who asked for the run, as the ledger records it (ADR 0014/0015). */
export const TRIGGER_LABEL = new Proxy({} as Record<WorkerRun["trigger"], string>, {
  get(_target, key) {
    return activeMessages().system.trigger[key as WorkerRun["trigger"]];
  },
});

/** The retry bound of ADR 0014/0015; the panel shows "tentativa 2/3". */
export const MAX_ATTEMPTS = 3;

/** True while the run has not reached a terminal state — what makes the screen poll. */
export function isActiveRun(run?: WorkerRun | null): boolean {
  return run?.status === "QUEUED" || run?.status === "RUNNING";
}

/**
 * True while a stop was requested but not yet honoured.
 *
 * The row is still ``QUEUED``/``RUNNING`` and keeps its slot (ADR 0014 decision 9), so the screen
 * says "cancelamento pedido", never "cancelada": the worker stops at the next batch boundary, and
 * pretending it stopped now would be the same lie as hiding the button.
 */
export function isCancelRequested(run?: WorkerRun | null): boolean {
  return isActiveRun(run) && Boolean(run?.cancel_requested_at);
}

/** Duration a person can read at a glance; milliseconds only matter for the instant runs. */
export function formatDuration(ms?: number | null): string {
  if (ms === undefined || ms === null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1).replace(".", ",")} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${Math.round(seconds % 60)} s`;
}

/**
 * The parts of the resolved configuration a person reads.
 *
 * The panel shows the **effective** configuration, so this is what the engine will actually use —
 * model, device and the host it will call — and not the preset's name again.
 */
export function describeConfig(config: Record<string, unknown> | undefined): string {
  const system = activeMessages().system;
  if (!config) return system.noModel;
  const parts: string[] = [];
  if (typeof config.model === "string") parts.push(config.model);
  if (typeof config.device === "string") parts.push(config.device);
  if (typeof config.host === "string") parts.push(config.host);
  if (typeof config.batch_size === "number") parts.push(system.batch.replace("{size}", String(config.batch_size)));
  if (typeof config.dimensions === "number")
    parts.push(system.dimensions.replace("{count}", String(config.dimensions)));
  if (Array.isArray(config.disable) && config.disable.length > 0) parts.push(system.stepsOff);
  return parts.length > 0 ? parts.join(" · ") : system.noParameters;
}

/** What one unit of a queue is, so "12 pendentes" is never ambiguous. */
export const UNIT_LABEL = new Proxy({} as Record<WorkerStatus["unit"], string>, {
  get(_target, key) {
    return activeMessages().system.unit[key as WorkerStatus["unit"]];
  },
});

/**
 * What a run's recorded worker options read as (#120).
 *
 * A row written before the column existed — or one that has not started — carries no options at
 * all, and saying "não registradas" is the honest answer: the columns it read cannot be recovered
 * from the fingerprint the stamp hashed.
 */
export function describeOptions(options: Record<string, unknown> | undefined): string {
  if (!options || Object.keys(options).length === 0) return activeMessages().system.optionsNotRecorded;
  return Object.entries(options)
    .map(([key, value]) => `${key}=${Array.isArray(value) ? value.join(",") : String(value)}`)
    .join(" · ");
}

/** Serialises the options for the textarea; an empty object reads as an empty box. */
export function optionsToText(options: Record<string, unknown> | undefined): string {
  if (!options || Object.keys(options).length === 0) return "";
  return JSON.stringify(options, null, 2);
}

/**
 * Parses the options textarea.
 *
 * Returns the object or an error sentence. The screen shows the sentence instead of sending a body
 * the API would reject with a generic 422 — the archivist typed the JSON, so the JSON is what has to
 * answer back.
 */
export function parseOptions(text: string): { options?: Record<string, unknown>; error?: string } {
  const trimmed = text.trim();
  if (trimmed.length === 0) return { options: {} };
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: activeMessages().system.optionsExample };
    }
    return { options: parsed as Record<string, unknown> };
  } catch {
    return { error: activeMessages().system.invalidJson };
  }
}

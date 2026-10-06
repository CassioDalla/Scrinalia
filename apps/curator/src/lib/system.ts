import type { WorkerRun, WorkerRunStatus, WorkerStatus } from "@/api/client";

/**
 * Human labels for the run lifecycle.
 *
 * The API speaks the enum; the operator reads Portuguese. Same rule as ``REVIEW_STATUS_LABEL``:
 * the mapping lives in the screen, which is what lets the contract stay in English.
 */
export const RUN_STATUS_LABEL: Record<WorkerRunStatus, string> = {
  QUEUED: "Na fila",
  RUNNING: "Em execução",
  SUCCESS: "Concluída",
  FAILED: "Falhou",
  INTERRUPTED: "Interrompida",
};

export const RUN_STATUS_TONE: Record<
  WorkerRunStatus,
  "neutral" | "ok" | "warn" | "danger" | "accent"
> = {
  QUEUED: "neutral",
  RUNNING: "accent",
  SUCCESS: "ok",
  FAILED: "danger",
  INTERRUPTED: "warn",
};

/** True while the run has not reached a terminal state — what makes the screen poll. */
export function isActiveRun(run?: WorkerRun | null): boolean {
  return run?.status === "QUEUED" || run?.status === "RUNNING";
}

export function hasActiveRun(workers: WorkerStatus[] | undefined): boolean {
  return (workers ?? []).some((worker) => isActiveRun(worker.active_run));
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
  if (!config) return "sem modelo";
  const parts: string[] = [];
  if (typeof config.model === "string") parts.push(config.model);
  if (typeof config.device === "string") parts.push(config.device);
  if (typeof config.host === "string") parts.push(config.host);
  if (typeof config.batch_size === "number") parts.push(`lote ${config.batch_size}`);
  if (typeof config.dimensions === "number") parts.push(`${config.dimensions} dims`);
  if (Array.isArray(config.disable) && config.disable.length > 0) parts.push("sem NER/parser");
  return parts.length > 0 ? parts.join(" · ") : "sem parâmetros";
}

/** What one unit of a queue is, so "12 pendentes" is never ambiguous. */
export const UNIT_LABEL: Record<WorkerStatus["unit"], string> = {
  staging: "registros de staging",
  document: "descrições",
  tag: "tags",
  pair: "pares",
};

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
      return { error: "As opções precisam ser um objeto JSON, por exemplo {\"force\": true}." };
    }
    return { options: parsed as Record<string, unknown> };
  } catch {
    return { error: "JSON inválido." };
  }
}

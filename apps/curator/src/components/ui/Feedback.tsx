import type { ReactNode } from "react";

import { ApiError } from "@/api/client";
import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-black/[0.07]", className)} />;
}

export function Spinner({ label = "Carregando…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-(--color-muted)">
      <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      {label}
    </div>
  );
}

/**
 * Empty states carry an explanation, never just "nothing here".
 *
 * The collection starts unarranged and unclassified, so the first thing this UI shows is a lot of
 * emptiness; a bare "no results" would read as a broken screen instead of as a task.
 */
export function EmptyState({ title, hint, action }: { title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-(--color-line) px-5 py-8">
      <p className="text-sm font-medium">{title}</p>
      {hint ? <p className="max-w-prose text-sm text-(--color-muted)">{hint}</p> : null}
      {action}
    </div>
  );
}

/**
 * The failure, plus the reference that makes it findable.
 *
 * Every response the API produces carries a request id, and the log line of the failing request
 * carries the same one. Showing it turns "a tela quebrou" into something the archivist can copy and
 * someone else can grep, without exposing anything about the internals.
 */
export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Erro inesperado.";
  const ref = error instanceof ApiError ? error.ref : undefined;
  return (
    <div className="rounded-lg bg-(--color-danger)/5 px-4 py-3 text-sm text-(--color-danger) ring-1 ring-(--color-danger)/20">
      {message}
      {ref ? <span className="mt-1 block text-xs opacity-70">referência: {ref}</span> : null}
    </div>
  );
}

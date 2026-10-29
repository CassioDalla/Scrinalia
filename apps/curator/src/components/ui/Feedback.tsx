import type { ReactNode } from "react";

import { ApiError } from "@/api/client";
import { Notice } from "@/components/ui/Notice";
import { cn } from "@/lib/cn";
import { refusalMessage } from "@/lib/messages";

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
 *
 * It is a `Notice` in the `danger` tone, and the three classes it adds back are the ones a failure
 * needs and a footnote does not: a failure is read at `text-sm`, with the padding of a block and a
 * larger corner. Sharing the surface is what keeps the red from being spelled four ways.
 */
export function ErrorState({ error }: { error: unknown }) {
  /**
   * The sentence comes from the refusal catalogue and falls back to the API's own (`lib/messages.ts`).
   *
   * Not `error.message`: a refusal carries a code, a Portuguese sentence, and — when it has facts to
   * state — a `details` payload, and printing the sentence here would freeze the server's language
   * into every screen the day the interface is translated. A code the catalogue does not know yet
   * still renders the API's sentence, so a refusal added later is never an empty line.
   */
  const message =
    error instanceof ApiError
      ? refusalMessage(error)
      : error instanceof Error
        ? error.message
        : "Erro inesperado.";
  const ref = error instanceof ApiError ? error.ref : undefined;
  return (
    <Notice tone="danger" as="div" className="rounded-lg px-4 py-3 text-sm">
      {message}
      {ref ? <span className="mt-1 block text-xs opacity-70">Referência: {ref}</span> : null}
    </Notice>
  );
}

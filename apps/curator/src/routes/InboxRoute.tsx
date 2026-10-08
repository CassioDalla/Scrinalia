import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { queries } from "@/api/queries";
import type { CurationQueue } from "@/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { formatCount } from "@/lib/format";

/**
 * Screens that exist today.
 *
 * The queues come from the API with the route that resolves them, which keeps the mapping on one
 * side. But a route in the contract is not a route that is *deployed* yet, and sending the
 * archivist to a blank page would be worse than saying "not yet" — so the front decides what it
 * can actually open, and the card says the rest is pending.
 */
const IMPLEMENTED = new Set([
  "/",
  "/acervo/lista",
  "/arranjo/plano",
  "/arranjo/diagnostico",
  "/assuntos/tags",
  "/assuntos/categorias",
  "/entidades/conflitos",
  "/qualidade/anomalias",
]);

function pathOf(route: string): string {
  return route.split("?")[0] ?? route;
}

function QueueCard({ queue }: { queue: CurationQueue }) {
  const target = pathOf(queue.route);
  const ready = IMPLEMENTED.has(target);
  const empty = queue.count === 0;

  const body = (
    <CardBody className="flex h-full flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <span className={empty ? "text-sm font-medium text-(--color-muted)" : "text-sm font-medium"}>
          {queue.label}
        </span>
        <span
          className={
            empty
              ? "text-2xl leading-none font-semibold tabular-nums text-(--color-muted)/50"
              : "text-2xl leading-none font-semibold tabular-nums"
          }
        >
          {formatCount(queue.count)}
        </span>
      </div>
      <p className="text-xs text-(--color-muted)">{queue.description}</p>
      <div className="mt-auto pt-1">
        {!ready ? (
          <Badge tone="neutral" title="Esta tela ainda não foi implementada">
            tela pendente
          </Badge>
        ) : empty ? (
          // Zero is not hidden: the archivist has to know the queue exists and is empty.
          <Badge tone="neutral">nada pendente</Badge>
        ) : (
          <span className="text-xs font-medium text-(--color-accent)">abrir →</span>
        )}
      </div>
    </CardBody>
  );

  const className = "h-full transition " + (empty ? "opacity-60" : "");

  if (!ready) {
    return (
      <Card className={className}>
        {body}
      </Card>
    );
  }

  return (
    <Link to={target} search={searchOf(queue.route)} className={className + " hover:ring-(--color-accent)/40"}>
      <Card className="h-full hover:ring-(--color-accent)/40">{body}</Card>
    </Link>
  );
}

/** Query string of the destination, so the card lands on the screen already filtered. */
function searchOf(route: string): Record<string, string> {
  const query = route.split("?")[1];
  if (!query) return {};
  return Object.fromEntries(new URLSearchParams(query));
}

export function InboxRoute() {
  const { data, isPending, error } = useQuery(queries.inbox());

  return (
    <>
      <PageHeader
        title="O que precisa de mim hoje"
        subtitle="Cada cartão leva à tela que resolve a pendência, já filtrada."
      />
      <div className="px-6 py-5">
        {error ? <ErrorState error={error} /> : null}

        {isPending ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-32" />
            ))}
          </div>
        ) : null}

        {data && data.queues && data.queues.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.queues.map((queue) => (
              <QueueCard key={queue.key} queue={queue} />
            ))}
          </div>
        ) : null}

        {data && (!data.queues || data.queues.length === 0) ? (
          <EmptyState
            title="Nenhuma fila configurada"
            hint="A API respondeu sem filas. Isso é um problema de contrato, não um acervo limpo."
          />
        ) : null}

        {data ? (
          <p className="mt-4 text-xs text-(--color-muted)">
            Contagens geradas em {new Date(data.generated_at).toLocaleString("pt-BR")}.
          </p>
        ) : null}
      </div>
    </>
  );
}

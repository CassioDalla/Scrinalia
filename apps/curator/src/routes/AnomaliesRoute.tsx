import { useQuery } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";

import { queries, ANOMALIES_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { formatCount, formatDate, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";
import { asNumber } from "@/lib/search";

const routeApi = getRouteApi("/qualidade/anomalias");

export type AnomaliesSearch = { offset?: number };

export function validateAnomaliesSearch(search: Record<string, unknown>): AnomaliesSearch {
  const offset = asNumber(search.offset);
  return { offset: offset !== undefined && offset > 0 ? offset : undefined };
}

/**
 * What the quality validator marked.
 *
 * The empty state is the point of this screen, not a decoration. An empty anomaly queue has two very
 * different causes and the archivist has to be able to tell them apart: the collection is clean, or
 * **no rule that flags anything is active**. Only ``VALIDATE`` and ``LLM_CHECK`` rules write an
 * anomaly — a ``REWRITE`` rule changes the text and never flags it — so an empty queue with no such
 * rule means the check never ran, and the screen says so and links to the rules.
 *
 * The counts by reason are read from the page in hand: the search has no "anomaly reason" facet, and
 * inventing a number the API does not return would be worse than saying "nesta página".
 */
export function AnomaliesRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const offset = search.offset ?? 0;
  const page = useQuery(queries.anomalies(offset));
  const inbox = useQuery(queries.inbox());

  const queue = (inbox.data?.queues ?? []).find((item) => item.key === "anomalies");
  const documents = page.data?.items ?? [];
  const total = page.data?.total ?? 0;

  // Only the reasons present in the page in hand; the label is the code the validator wrote.
  const reasons = new Map<string, number>();
  for (const document of documents) {
    for (const reason of document.anomaly_reasons ?? []) {
      reasons.set(reason, (reasons.get(reason) ?? 0) + 1);
    }
  }

  return (
    <>
      <PageHeader
        title="Anomalias detectadas"
        subtitle={
          page.data
            ? `${formatCount(total)} descrições aguardando revisão`
            : "Lendo a fila de anomalias…"
        }
        actions={
          <Link to="/qualidade/regras">
            <Button size="sm">Regras de limpeza</Button>
          </Link>
        }
      />

      <div className="grid max-w-4xl gap-4 px-6 py-5">
        {inbox.data && (queue?.count ?? 0) === 0 ? (
          <EmptyState
            title="Nenhuma anomalia detectada"
            hint={
              <>
                Isso quer dizer que nenhuma regra <code>VALIDATE</code> ou <code>LLM_CHECK</code> está
                ativa — não que o acervo esteja impecável. Uma regra <code>REWRITE</code> muda o texto e
                nunca marca anomalia. Veja as{" "}
                <Link to="/qualidade/regras" className="underline">
                  regras de limpeza
                </Link>
                .
              </>
            }
          />
        ) : null}

        {reasons.size > 0 ? (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-(--color-muted)">motivos nesta página:</span>
            {[...reasons.entries()].map(([reason, count]) => (
              <Badge key={reason} tone="warn" title="Código gravado pelo validador de qualidade">
                {reason} · {formatCount(count)}
              </Badge>
            ))}
          </div>
        ) : null}

        {page.error ? <ErrorState error={page.error} /> : null}
        {page.isPending ? <Spinner /> : null}

        <ul className="grid gap-2">
          {documents.map((document) => (
            <li key={document.description_id}>
              <Card className="transition hover:ring-(--color-warn)/40">
                <CardBody className="grid gap-2">
                  <div className="flex items-start justify-between gap-3">
                    <Link
                      to="/acervo/$descriptionId"
                      params={{ descriptionId: document.description_id }}
                      className="min-w-0 text-sm font-medium hover:underline"
                    >
                      {document.final_title || document.original_title}
                    </Link>
                    <Badge tone={REVIEW_STATUS_TONE[document.review_status]}>
                      {REVIEW_STATUS_LABEL[document.review_status]}
                    </Badge>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
                    <span>{formatDate(document.document_date)}</span>
                    {document.level ? <span>· {document.level}</span> : null}
                    {document.reference_code ? (
                      <code className="rounded bg-black/[0.05] px-1">{document.reference_code}</code>
                    ) : null}
                  </div>

                  {(document.anomaly_reasons ?? []).length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {(document.anomaly_reasons ?? []).map((reason) => (
                        <Badge key={reason} tone="warn">
                          {reason}
                        </Badge>
                      ))}
                    </div>
                  ) : null}

                  <p className="text-xs text-(--color-muted)">
                    A correção é a revisão humana da ficha: editar salva o antes/depois na trilha e marca
                    a descrição como revisada.
                  </p>
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>

        {total > ANOMALIES_PAGE_SIZE ? (
          <div className="flex items-center justify-between text-sm">
            <Button
              size="sm"
              disabled={offset === 0}
              onClick={() =>
                navigate({ to: "/qualidade/anomalias", search: { offset: Math.max(0, offset - ANOMALIES_PAGE_SIZE) } })
              }
            >
              ← Anterior
            </Button>
            <span className="text-xs text-(--color-muted)">
              {formatCount(offset + 1)}–{formatCount(Math.min(offset + ANOMALIES_PAGE_SIZE, total))} de{" "}
              {formatCount(total)}
            </span>
            <Button
              size="sm"
              disabled={offset + ANOMALIES_PAGE_SIZE >= total}
              onClick={() =>
                navigate({ to: "/qualidade/anomalias", search: { offset: offset + ANOMALIES_PAGE_SIZE } })
              }
            >
              Próxima →
            </Button>
          </div>
        ) : null}
      </div>
    </>
  );
}

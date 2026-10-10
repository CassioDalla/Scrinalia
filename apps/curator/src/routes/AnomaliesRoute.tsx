import { useQuery } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";

import { queries, ANOMALIES_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { PageBody } from "@/components/layout/PageBody";
import { cn } from "@/lib/cn";
import { formatCount, formatDate, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";
import { ANOMALY_REASON_HINT, anomalyReasonCode, anomalyReasonLabel } from "@/lib/quality";
import { asNumber } from "@/lib/search";

const routeApi = getRouteApi("/qualidade/anomalias");

export type AnomaliesSearch = { offset?: number; motivo?: string };

export function validateAnomaliesSearch(search: Record<string, unknown>): AnomaliesSearch {
  const offset = asNumber(search.offset);
  // The key travels as the facet wrote it — a bare code, or ``RULE_MATCH:<rule>`` — so the route
  // accepts a string and the API validates it against the same expression the facet groups by.
  const motivo = typeof search.motivo === "string" && search.motivo.length > 0 ? search.motivo : undefined;
  return {
    offset: offset !== undefined && offset > 0 ? offset : undefined,
    motivo,
  };
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
 * The counts by reason are the search's own facet, over the whole filtered set — the screen used to
 * count the page in hand and say so, because the API had no dimension to offer. They are also the
 * filter: clicking one narrows the list to that reason, and the facet's own selection does not zero
 * its own options, so the other reasons stay visible and the archivist can switch without clearing
 * first.
 *
 * ``LLM_SUSPECT`` is one bucket whatever the model wrote, while ``RULE_MATCH`` keeps the rule's name:
 * a rule is a catalogue entry, and "which rule flagged this?" is the question worth asking.
 */
export function AnomaliesRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const offset = search.offset ?? 0;
  const reason = search.motivo;
  const page = useQuery(queries.anomalies(offset, reason));
  const inbox = useQuery(queries.inbox());

  const queue = (inbox.data?.queues ?? []).find((item) => item.key === "anomalies");
  const documents = page.data?.items ?? [];
  const total = page.data?.total ?? 0;
  // The facet, over the whole filtered set — not a recount of the page in hand.
  const reasons = page.data?.facets?.anomaly_reason ?? [];

  return (
    <>
      <PageHeader
        screen="anomalies"
        pending={page.isPending}
        status={page.data ? `${formatCount(total)} descrições aguardando revisão` : undefined}
        actions={
          <Link to="/qualidade/regras">
            <Button size="sm">Regras</Button>
          </Link>
        }
      />

      <PageBody>
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

        {reasons.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-(--color-muted)">motivos no acervo filtrado:</span>
            {reasons.map((item) => (
              <button
                key={item.key}
                type="button"
                title={
                  ANOMALY_REASON_HINT[anomalyReasonCode(item.key)] ??
                  "Código gravado pelo validador de qualidade"
                }
                onClick={() =>
                  navigate({
                    to: "/qualidade/anomalias",
                    search: { motivo: reason === item.key ? undefined : item.key, offset: undefined },
                  })
                }
                className={cn(
                  "rounded-full px-2 py-0.5 ring-1 transition",
                  reason === item.key
                    ? "bg-(--color-accent)/10 text-(--color-accent) ring-(--color-accent)/30"
                    : "bg-(--color-warn)/5 text-(--color-warn) ring-(--color-warn)/20 hover:bg-(--color-warn)/10",
                )}
              >
                {anomalyReasonLabel(item.key)} · {formatCount(item.count)}
              </button>
            ))}
            {reason ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => navigate({ to: "/qualidade/anomalias", search: { offset: undefined } })}
              >
                limpar filtro
              </Button>
            ) : null}
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
                      {(document.anomaly_reasons ?? []).map((stored) => (
                        <Badge key={stored} tone="warn" title={stored}>
                          {anomalyReasonLabel(stored)}
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
                navigate({
                  to: "/qualidade/anomalias",
                  search: { motivo: reason, offset: Math.max(0, offset - ANOMALIES_PAGE_SIZE) || undefined },
                })
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
                navigate({
                  to: "/qualidade/anomalias",
                  search: { motivo: reason, offset: offset + ANOMALIES_PAGE_SIZE },
                })
              }
            >
              Próxima →
            </Button>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}

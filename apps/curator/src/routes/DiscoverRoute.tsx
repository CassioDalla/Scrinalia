import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { createMacroCategory, suggestMacroCategories, type MacroCategorySuggested } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { ACTION } from "@/lib/copy";
import { formatCount } from "@/lib/format";
import { routeMessage } from "@/lib/messages";

/**
 * Discovering a drawer the vocabulary does not have yet.
 *
 * The vocabulary went from 5 to 8 subject drawers because the measurement demanded it: ``igrejas``
 * reached 2,467 documents — the heaviest tag in the collection — and there was no "Religião" for it
 * to fall into. No classifier label fixes a drawer that does not exist.
 *
 * Two honest constraints shape the screen. The suggestion runs the real clustering engine (BERTopic,
 * about ten seconds), so it is a deliberate click and never a page load. And a small corpus answers
 * ``total_suggestions: 0`` with a message instead of a 422 — the screen renders the message, because
 * an empty list would read as "the collection has no subjects".
 */
export function DiscoverRoute() {
  const [sourceType, setSourceType] = useState<"tags" | "documents">("tags");
  /** ``null`` means "the code's defaults": nothing is sent, and the route resolves them itself. */
  const [columns, setColumns] = useState<string[] | null>(null);
  const [dismissed, setDismissed] = useState<number[]>([]);
  const catalogue = useQuery(queries.clusteringColumns());

  const selected = columns ?? catalogue.data?.defaults ?? [];
  const noColumnChosen = sourceType === "documents" && selected.length === 0;

  const toggleColumn = (name: string) => {
    setColumns((current) => {
      const base = current ?? catalogue.data?.defaults ?? [];
      return base.includes(name) ? base.filter((item) => item !== name) : [...base, name];
    });
  };

  const suggest = useMutation({
    mutationFn: () =>
      suggestMacroCategories(
        sourceType === "documents" && columns !== null
          ? { source_type: "documents", columns_to_extract: columns }
          : { source_type: sourceType },
      ),
  });

  const suggestions = (suggest.data?.categories ?? []).filter(
    (category) => !dismissed.includes(category.topic_id),
  );

  return (
    <>
      <PageHeader
        screen="discover"
        actions={
          <Link to="/assuntos/categorias">
            <Button size="sm">Categorias Atuais</Button>
          </Link>
        }
      />

      <PageBody>
        <Card>
          <CardHeader className="text-sm font-semibold">Agrupar por tema</CardHeader>
          <CardBody className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Roda o motor de agrupamento de verdade: leva alguns segundos e é um clique deliberado. Os
              agrupamentos abaixo são só <strong>propostas</strong> — nada entra no vocabulário sem aprovação.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant={sourceType === "tags" ? "primary" : "secondary"}
                onClick={() => setSourceType("tags")}
              >
                A partir das Tags
              </Button>
              <Button
                size="sm"
                variant={sourceType === "documents" ? "primary" : "secondary"}
                onClick={() => setSourceType("documents")}
              >
                A partir dos Documentos
              </Button>
              <Button
                variant="primary"
                disabled={suggest.isPending || noColumnChosen}
                onClick={() => suggest.mutate()}
              >
                {suggest.isPending ? "Agrupando… (pode levar alguns segundos)" : "Propor Categorias"}
              </Button>
            </div>
            {/*
              The columns the clustering reads, offered only for the documents source: the route
              refuses them with ``source_type='tags'``, and a control that a body would reject is a
              control the screen must not show (#174). The list comes from the route that validates
              it, so the screen never types a column name.
            */}
            {sourceType === "documents" ? (
              <div className="grid gap-1">
                <span className="text-xs text-(--color-muted)">
                  O clustering lê o texto destas colunas. Desmarcar todas não é uma escolha válida.
                </span>
                {catalogue.isError ? <ErrorState error={catalogue.error} /> : null}
                {catalogue.data ? (
                  <div className="flex flex-wrap items-center gap-3">
                    {catalogue.data.columns.map((column) => (
                      <label key={column} className="flex items-center gap-1 text-xs">
                        <input type="checkbox" checked={selected.includes(column)} onChange={() => toggleColumn(column)} />
                        <code>{column}</code>
                        {catalogue.data.defaults.includes(column) ? (
                          <span className="text-(--color-muted)">(padrão)</span>
                        ) : null}
                      </label>
                    ))}
                  </div>
                ) : null}
                {noColumnChosen ? (
                  <span className="text-xs text-(--color-danger)">Escolha ao menos uma coluna.</span>
                ) : null}
              </div>
            ) : null}
            {suggest.error ? <ErrorState error={suggest.error} /> : null}
          </CardBody>
        </Card>

        {suggest.data ? (
          <>
            {routeMessage(suggest.data) ? (
              <Notice tone="warn">
                {routeMessage(suggest.data)}
              </Notice>
            ) : null}

            {suggestions.length === 0 && !routeMessage(suggest.data) ? (
              <EmptyState
                title="Nenhum agrupamento novo"
                hint="O agrupamento não encontrou tema que já não esteja coberto pelas categorias atuais."
              />
            ) : null}
          </>
        ) : null}

        <ul className="grid gap-2">
          {suggestions.map((category) => (
            <li key={category.topic_id}>
              <SuggestionCard category={category} onDismiss={() => setDismissed((c) => [...c, category.topic_id])} />
            </li>
          ))}
        </ul>
      </PageBody>
    </>
  );
}

/** One agrupamento: an editable name, the weight and the real samples it was formed from. */
function SuggestionCard({
  category,
  onDismiss,
}: {
  category: MacroCategorySuggested;
  onDismiss: () => void;
}) {
  const [name, setName] = useState(category.suggested_name);

  const create = useMutation({
    mutationFn: () => createMacroCategory({ name: name.trim(), description: null, classifier_label: null }),
  });

  return (
    /*
      Each agrupamento collapses to its weight and its proposed name. The proposal is a *question* ("chamar
      esta categoria de X?"), and a screen of five open forms answers questions the archivist has not
      asked yet; the samples that justify the name are one click away, next to the button.
    */
    <Disclosure
      toggleLabel="Ver as amostras do Agrupamento"
      header={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="accent">{formatCount(category.estimate_count)} estimativas</Badge>
          <Badge tone="neutral">tema #{category.topic_id}</Badge>
          <span className="text-sm font-medium">{category.suggested_name}</span>
        </div>
      }
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={name.trim().length === 0 || create.isPending || create.isSuccess}
            onClick={() => create.mutate()}
          >
            {create.isSuccess ? "criada" : create.isPending ? ACTION.create.pending : `${ACTION.create.label} categoria`}
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            {ACTION.discard.label}
          </Button>
        </div>
      }
    >
      <div className="grid gap-2">
        <Field label="Nome da Categoria">
          <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
        </Field>

        {(category.real_samples ?? []).length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {(category.real_samples ?? []).slice(0, 12).map((sample) => (
              <span key={sample} className="rounded-full bg-black/5 px-2 py-0.5 text-[11px]">
                {sample}
              </span>
            ))}
          </div>
        ) : null}

        <p className="text-xs text-(--color-muted)">
          A Categoria só passa a valer quando o classificador rodar de novo.
        </p>

        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}

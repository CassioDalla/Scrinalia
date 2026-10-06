import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { createMacroCategory, suggestMacroCategories, type MacroCategorySuggested } from "@/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { formatCount } from "@/lib/format";

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
  const [dismissed, setDismissed] = useState<number[]>([]);

  const suggest = useMutation({
    mutationFn: () => suggestMacroCategories({ source_type: sourceType }),
  });

  const suggestions = (suggest.data?.categories ?? []).filter(
    (category) => !dismissed.includes(category.topic_id),
  );

  return (
    <>
      <PageHeader
        title="Descobrir gavetas"
        subtitle="Agrupa o vocabulário por tema para achar o assunto que ainda não tem gaveta."
        actions={
          <Link to="/assuntos/categorias">
            <Button size="sm">Gavetas atuais</Button>
          </Link>
        }
      />

      <div className="grid max-w-4xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-accent)/5 px-3 py-2 text-xs text-(--color-accent) ring-1 ring-(--color-accent)/20">
          O vocabulário cresceu de 5 para 8 gavetas porque a medição pediu: <code>igrejas</code> alcança
          <strong> 2.467 documentos</strong> — a maior tag do acervo — e não havia "Religião" para ela.
          Nenhum rótulo conserta uma gaveta inexistente. As gavetas que saíram (<em>Instituição</em>,{" "}
          <em>Localidade</em>, <em>Pessoa</em>) não eram ruins: são proveniência e geografia, não assunto.
        </p>

        <Card>
          <CardHeader className="text-sm font-semibold">Agrupar por tema</CardHeader>
          <CardBody className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Roda o motor de agrupamento de verdade: leva alguns segundos e é um clique deliberado. Os
              clusters abaixo são só <strong>propostas</strong> — nada entra no vocabulário sem você
              cadastrar.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant={sourceType === "tags" ? "primary" : "secondary"}
                onClick={() => setSourceType("tags")}
              >
                a partir das tags
              </Button>
              <Button
                size="sm"
                variant={sourceType === "documents" ? "primary" : "secondary"}
                onClick={() => setSourceType("documents")}
              >
                a partir dos documentos
              </Button>
              <Button variant="primary" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
                {suggest.isPending ? "Agrupando… (pode levar alguns segundos)" : "Propor gavetas"}
              </Button>
            </div>
            {suggest.error ? <ErrorState error={suggest.error} /> : null}
          </CardBody>
        </Card>

        {suggest.data ? (
          <>
            {suggest.data.message ? (
              <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
                {suggest.data.message}
              </p>
            ) : null}

            {suggestions.length === 0 && !suggest.data.message ? (
              <EmptyState
                title="Nenhum cluster novo"
                hint="O agrupamento não encontrou tema que já não esteja coberto pelas gavetas atuais."
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
      </div>
    </>
  );
}

/** One cluster: an editable name, the weight and the real samples it was formed from. */
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
      Each cluster collapses to its weight and its proposed name. The proposal is a *question* ("chamar
      esta gaveta de X?"), and a screen of five open forms answers questions the archivist has not
      asked yet; the samples that justify the name are one click away, next to the button.
    */
    <Disclosure
      toggleLabel="Ver as amostras do cluster"
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
            {create.isSuccess ? "cadastrada" : create.isPending ? "Cadastrando…" : "Cadastrar como gaveta"}
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            descartar
          </Button>
        </div>
      }
    >
      <div className="grid gap-2">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Nome da gaveta</span>
          <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
        </label>

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
          A gaveta só passa a valer quando o classificador rodar de novo: o carimbo do worker é o hash
          do conjunto de rótulos.
        </p>

        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}

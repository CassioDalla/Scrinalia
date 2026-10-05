import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createMacroCategory, updateMacroCategory, type MacroCategory } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input, Textarea } from "@/components/ui/Input";
import { formatCount } from "@/lib/format";

/**
 * The drawers the subject classifier reads.
 *
 * Two things this screen has to say out loud, because the data does not say them by itself:
 *
 * * the **retired** drawers are not mistakes. ``Pessoa``, ``Localidade`` and ``Instituição`` left
 *   the subject axis because they are provenance and geography — ``ippuc`` reaches 2,376 documents
 *   and ``curitiba`` 1,865 — and they were competing with ``alvenaria`` for the same slot. They
 *   stay listed, deactivated, because the FK is ``SET NULL`` and deleting one would erase the fact
 *   that it existed;
 * * ``classifier_label`` is a curator override, **not** an improvement. Measured on 44 hand-labelled
 *   tags, a phrase instead of a bare name scores **0.000** with 65% of the tags in one drawer
 *   (`testing/evaluation/macro_category_quality.py`). The label exists so a curator can adjust the
 *   wording without a deploy; someone who fills it expecting a gain will be disappointed, and the
 *   screen must say so before they do.
 */
export function CategoriesRoute() {
  const queryClient = useQueryClient();
  const categories = useQuery(queries.macroCategories());

  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "macro-categories"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const create = useMutation({
    mutationFn: () =>
      createMacroCategory({ name: draftName.trim(), description: draftDescription.trim() || null, classifier_label: null }),
    onSuccess: () => {
      setDraftName("");
      setDraftDescription("");
      invalidate();
    },
  });

  const active = (categories.data ?? []).filter((category) => category.is_active);
  const retired = (categories.data ?? []).filter((category) => !category.is_active);
  const totalDocuments = active.reduce((sum, category) => sum + (category.document_count ?? 0), 0);

  return (
    <>
      <PageHeader
        title="Gavetas de assunto"
        subtitle={
          categories.data
            ? `${active.length} ativas · ${retired.length} aposentadas · ${formatCount(totalDocuments)} descrições com gaveta`
            : "Lendo o vocabulário…"
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
          <strong>A frase não melhora a classificação.</strong> Medido em 44 tags rotuladas à mão: dar uma frase ao
          modelo em vez do nome nu leva a acurácia a <strong>0.000</strong>, com 65% das tags numa única gaveta. O
          rótulo existe para o curador ajustar a redação sem deploy — não espere ganho dele.
        </p>

        {categories.error ? <ErrorState error={categories.error} /> : null}
        {categories.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-24" />
            ))}
          </div>
        ) : null}

        {active.length > 0 ? (
          <section className="grid gap-2">
            <h2 className="text-sm font-semibold">Ativas</h2>
            {active.map((category) => (
              <CategoryCard key={category.category_id} category={category} onChanged={invalidate} />
            ))}
          </section>
        ) : null}

        {retired.length > 0 ? (
          <section className="grid gap-2">
            <h2 className="text-sm font-semibold">Aposentadas</h2>
            <p className="text-xs text-(--color-muted)">
              Saíram do eixo de assunto porque são proveniência e geografia, não assunto. Nunca foram apagadas: a
              chave estrangeira é <code>SET NULL</code>, e apagar uma gaveta apagaria o registro de que ela existiu.
            </p>
            {retired.map((category) => (
              <CategoryCard key={category.category_id} category={category} onChanged={invalidate} />
            ))}
          </section>
        ) : null}

        <Card>
          <CardHeader className="text-sm font-semibold">Cadastrar uma gaveta</CardHeader>
          <CardBody className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Uma gaveta nova só passa a valer quando o classificador rodar de novo: o carimbo do worker é o
              <strong> hash do conjunto de rótulos</strong>, então mudar o vocabulário devolve as tags à fila sozinho.
            </p>
            <Input
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              placeholder="nome, ex.: Saúde"
              maxLength={100}
            />
            <Textarea
              value={draftDescription}
              onChange={(event) => setDraftDescription(event.target.value)}
              placeholder="descrição para o curador (nunca vai para o modelo)"
              rows={2}
            />
            <div>
              <Button
                variant="primary"
                disabled={draftName.trim().length === 0 || create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending ? "Cadastrando…" : "Cadastrar"}
              </Button>
            </div>
            {create.error ? <ErrorState error={create.error} /> : null}
          </CardBody>
        </Card>
      </div>
    </>
  );
}

/**
 * One drawer, editable in place.
 *
 * The edits are partial on purpose: ``PATCH`` only touches the fields sent, so renaming a drawer and
 * deactivating it are different decisions that happen to share a card. The name is not sent unless it
 * changed, because a rename is a statement about the vocabulary the classifier reads.
 */
function CategoryCard({ category, onChanged }: { category: MacroCategory; onChanged: () => void }) {
  const [name, setName] = useState(category.name);
  const [description, setDescription] = useState(category.description ?? "");
  const [label, setLabel] = useState(category.classifier_label ?? "");

  const save = useMutation({
    mutationFn: (changes: { name?: string; description?: string | null; classifier_label?: string | null; is_active?: boolean }) =>
      updateMacroCategory(category.category_id, changes),
    onSuccess: onChanged,
  });

  const dirty =
    name !== category.name ||
    description !== (category.description ?? "") ||
    label !== (category.classifier_label ?? "");

  return (
    <Card>
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-medium">{category.name}</span>
            {category.is_active ? <Badge tone="ok">ativa</Badge> : <Badge tone="neutral">aposentada</Badge>}
            <Badge tone="accent" title="Descrições com pelo menos uma tag nesta gaveta">
              {formatCount(category.document_count ?? 0)} descrições
            </Badge>
          </div>
          <Button
            size="sm"
            variant={category.is_active ? "ghost" : "secondary"}
            disabled={save.isPending}
            onClick={() => save.mutate({ is_active: !category.is_active })}
          >
            {category.is_active ? "aposentar" : "reativar"}
          </Button>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nome</span>
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Rótulo que o modelo lê (vazio = o nome)</span>
            <Input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder={category.name}
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Descrição (documentação do curador, nunca vai ao modelo)</span>
          <Input value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={!dirty || save.isPending || name.trim().length === 0}
            onClick={() =>
              save.mutate({
                name: name.trim(),
                description: description.trim() || null,
                classifier_label: label.trim() || null,
              })
            }
          >
            {save.isPending ? "Salvando…" : "Salvar"}
          </Button>
          {dirty ? <span className="text-xs text-(--color-muted)">alterações não salvas</span> : null}
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
      </CardBody>
    </Card>
  );
}

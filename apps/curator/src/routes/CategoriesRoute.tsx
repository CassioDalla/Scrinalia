import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createMacroCategory, updateMacroCategory, type MacroCategory } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { ACTION } from "@/lib/copy";
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
        screen="categories"
        pending={categories.isPending}
        status={
          categories.data
            ? `${active.length} ativas · ${retired.length} aposentadas · ${formatCount(totalDocuments)} descrições com gaveta`
            : undefined
        }
      />

      <PageBody>
        <Notice tone="warn">
          <strong>A frase não melhora a classificação.</strong> Medido em 44 tags rotuladas à mão: dar uma frase ao
          modelo em vez do nome nu leva a acurácia a <strong>0.000</strong>, com 65% das tags numa única gaveta. O
          rótulo existe para o curador ajustar a redação sem deploy — não espere ganho dele.
        </Notice>

        {categories.error ? <ErrorState error={categories.error} /> : null}
        {categories.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-24" />
            ))}
          </div>
        ) : null}

        {/* The write first, the catalogue after — and every drawer opens on demand. */}
        <Disclosure
          triggerLabel="+ Nova gaveta"
          toggleLabel="Criar uma gaveta"
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">Criar uma gaveta</span>
              <span className="text-xs text-(--color-muted)">
                Uma gaveta nova só passa a valer quando o classificador rodar de novo.
              </span>
            </div>
          }
        >
          <div className="grid gap-2">
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
                {create.isPending ? ACTION.create.pending : ACTION.create.label}
              </Button>
            </div>
            {create.error ? <ErrorState error={create.error} /> : null}
          </div>
        </Disclosure>

        {active.length > 0 ? (
          <section className="grid gap-2">
            <SectionTitle>Ativas</SectionTitle>
            {active.map((category) => (
              <CategoryCard key={category.category_id} category={category} onChanged={invalidate} />
            ))}
          </section>
        ) : null}

        {retired.length > 0 ? (
          <section className="grid gap-2">
            <SectionTitle>Aposentadas</SectionTitle>
            <p className="text-xs text-(--color-muted)">
              Saíram do eixo de assunto porque são proveniência e geografia, não assunto. Nunca foram apagadas: a
              chave estrangeira é <code>SET NULL</code>, e excluir uma gaveta excluiria o registro de que ela existiu.
            </p>
            {retired.map((category) => (
              <CategoryCard key={category.category_id} category={category} onChanged={invalidate} />
            ))}
          </section>
        ) : null}

      </PageBody>
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
    <Disclosure
      toggleLabel="Editar esta gaveta"
      className={category.is_active ? undefined : "opacity-80"}
      header={
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium">{category.name}</span>
          {category.is_active ? <Badge tone="ok">ativa</Badge> : <Badge tone="neutral">aposentada</Badge>}
          <Badge tone="accent" title="Descrições com pelo menos uma tag nesta gaveta">
            {formatCount(category.document_count ?? 0)} descrições
          </Badge>
          {category.description ? (
            <span className="w-full text-xs text-(--color-muted)">{category.description}</span>
          ) : null}
        </div>
      }
      actions={
        <Button
          size="sm"
          variant={category.is_active ? "ghost" : "secondary"}
          disabled={save.isPending}
          onClick={() => save.mutate({ is_active: !category.is_active })}
        >
          {category.is_active ? ACTION.retire.label : ACTION.reactivate.label}
        </Button>
      }
    >
      <div className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Nome">
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
          </Field>
          <Field label="Rótulo que o modelo lê (vazio = o nome)">
            <Input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder={category.name}
            />
          </Field>
        </div>

        <Field label="Descrição (documentação do curador, nunca vai ao modelo)">
          <Input value={description} onChange={(event) => setDescription(event.target.value)} />
        </Field>

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
            {save.isPending ? ACTION.save.pending : ACTION.save.label}
          </Button>
          {dirty ? <span className="text-xs text-(--color-muted)">alterações não salvas</span> : null}
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
      </div>
    </Disclosure>
  );
}

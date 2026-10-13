import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { createMacroCategory, updateMacroCategory, type MacroCategory } from "@/api/client";
import { CATEGORY_DOCUMENTS_PAGE_SIZE, queries } from "@/api/queries";
import { DescriptionExpansion } from "@/components/description/DescriptionExpansion";
import { DescriptionPreview } from "@/components/description/DescriptionPreview";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageBody } from "@/components/layout/PageBody";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { Tabs } from "@/components/ui/Tabs";
import { ACTION } from "@/lib/copy";
import { formatCount } from "@/lib/format";
import { asNumber, asString } from "@/lib/search";

/**
 * ``getRouteApi`` instead of importing the route object: the route is declared in ``router.tsx`` and
 * the component lives here, and importing one from the other would be a cycle.
 */
const routeApi = getRouteApi("/assuntos/categorias");

/**
 * The URL is the state, as on every other list.
 *
 * Three things travel together and each one is a question the archivist asked: which category is
 * open (one at a time — the page is a list of drawers, not a dashboard), which page of **that**
 * category's descriptions is showing, and which description the panel is previewing. Keeping them
 * here is what makes the back button close the panel, and what lets a colleague be sent the exact
 * view instead of a category name to search for again.
 */
export type CategoriesSearch = {
  aberta?: number;
  descricao?: string;
  offset?: number;
};

export function validateCategoriesSearch(search: Record<string, unknown>): CategoriesSearch {
  return {
    aberta: asNumber(search.aberta),
    descricao: asString(search.descricao),
    offset: asNumber(search.offset),
  };
}

/** The two questions one card answers: what is inside it, and what it is called. */
const CARD_TABS = [
  { id: "descricoes", label: "Descrições" },
  { id: "editar", label: "Editar" },
];

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
 *
 * Each card opens on the descriptions the drawer holds — the read the list screen already exposes,
 * with the same filter — because a catalogue that shows the weight of a drawer and cannot be looked
 * inside answers the wrong half of the question.
 */
export function CategoriesRoute() {
  const queryClient = useQueryClient();
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const categories = useQuery(queries.macroCategories());

  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");

  /**
   * ``offset: changes.offset`` and not a literal: opening another category has to return to **its**
   * first page — page 3 of the previous category means nothing — and a caller that wants the first
   * page sends no page at all. The literal-after-the-spread shape is what
   * ``testing/unit/curator/test_curator_search_state.py`` exists to catch, because it silently
   * discarded the page a caller had just set.
   */
  const patch = (changes: Partial<CategoriesSearch>) =>
    navigate({ to: "/assuntos/categorias", search: { ...search, ...changes, offset: changes.offset } });

  /**
   * The preview is not a filter, so it does not go through ``patch``: opening a row on page 3 and
   * closing the panel has to leave the archivist on page 3. Spreading the current search and
   * changing one key is what says that, and it is why this is a second fold and not a flag on the
   * first one.
   */
  const showPreview = (descriptionId: string | undefined) =>
    navigate({ to: "/assuntos/categorias", search: { ...search, descricao: descriptionId } });

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
            ? `${active.length} ativas · ${retired.length} aposentadas · ${formatCount(totalDocuments)} descrições com categoria`
            : undefined
        }
      />

      <PageBody>
        <Notice tone="warn">
          <strong>A frase não melhora a classificação.</strong> Medido em 44 tags rotuladas à mão: dar uma frase ao
          modelo em vez do nome nu leva a acurácia a <strong>0.000</strong>, com 65% das tags numa única categoria. O
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
          triggerLabel="+ Nova Categoria"
          toggleLabel="Criar uma Categoria"
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">Criar uma Categoria</span>
              <span className="text-xs text-(--color-muted)">
                Uma categoria nova só passa a valer quando o classificador rodar de novo.
              </span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Uma categoria nova só passa a valer quando o classificador rodar de novo: o carimbo do worker é o
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
              <CategoryCard
                key={category.category_id}
                category={category}
                open={search.aberta === category.category_id}
                offset={search.aberta === category.category_id ? (search.offset ?? 0) : 0}
                onOpenChange={(next) => patch({ aberta: next ? category.category_id : undefined })}
                onPage={(offset) => patch({ offset })}
                onPreview={showPreview}
                onChanged={invalidate}
              />
            ))}
          </section>
        ) : null}

        {retired.length > 0 ? (
          <section className="grid gap-2">
            <SectionTitle>Aposentadas</SectionTitle>
            <p className="text-xs text-(--color-muted)">
              Saíram do eixo de assunto porque são proveniência e geografia, não assunto. Nunca foram excluídas: a
              chave estrangeira é <code>SET NULL</code>, e excluir uma categoria excluiria o registro de que ela existiu.
            </p>
            {retired.map((category) => (
              <CategoryCard
                key={category.category_id}
                category={category}
                open={search.aberta === category.category_id}
                offset={search.aberta === category.category_id ? (search.offset ?? 0) : 0}
                onOpenChange={(next) => patch({ aberta: next ? category.category_id : undefined })}
                onPage={(offset) => patch({ offset })}
                onPreview={showPreview}
                onChanged={invalidate}
              />
            ))}
          </section>
        ) : null}

      </PageBody>

      {/*
        The panel is rendered by the screen and not by the row: the description being previewed is in
        the URL, so the panel survives a refetch of the list it was opened from — and a link that
        carries ``descricao`` opens on the record even when the current page does not list it.
      */}
      {search.descricao ? (
        <DescriptionPreview
          descriptionId={search.descricao}
          editTab="descricao"
          onClose={() => showPreview(undefined)}
        />
      ) : null}
    </>
  );
}

/**
 * One drawer, opened on the descriptions it holds.
 *
 * The card's body has two questions because it is one object being both read and edited, and the
 * archivist arrives at this screen with the first one: "what is in `Saúde`?" The edit form is a tab
 * away and not a click on a different screen. ``Disclosure``'s header stays text and badges only —
 * a control inside the toggle would be a button inside a button.
 */
function CategoryCard({
  category,
  open,
  offset,
  onOpenChange,
  onPage,
  onPreview,
  onChanged,
}: {
  category: MacroCategory;
  open: boolean;
  offset: number;
  onOpenChange: (open: boolean) => void;
  onPage: (offset: number) => void;
  onPreview: (descriptionId: string) => void;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<string>("descricoes");

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
      open={open}
      onOpenChange={onOpenChange}
      toggleLabel="Ver as descrições desta Categoria"
      className={category.is_active ? undefined : "opacity-80"}
      header={
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium">{category.name}</span>
          {category.is_active ? <Badge tone="ok">ativa</Badge> : <Badge tone="neutral">aposentada</Badge>}
          <Badge tone="accent" title="Descrições com pelo menos uma tag nesta categoria">
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
      <div className="grid gap-3">
        <Tabs items={CARD_TABS} active={tab} onChange={setTab} />

        {tab === "editar" ? (
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
        ) : (
          <DescriptionExpansion
            params={{ macro_category_id: category.category_id }}
            pageSize={CATEGORY_DOCUMENTS_PAGE_SIZE}
            offset={offset}
            onPage={onPage}
            onPreview={onPreview}
            empty={
              category.is_active
                ? {
                    title: "Nenhuma descrição nesta categoria",
                    hint: "Nenhuma tag desta categoria está ligada a uma descrição ainda. As tags sem categoria de assunto estão na aba Classificar, em Tags.",
                  }
                : {
                    title: "Categoria aposentada e vazia",
                    hint: "Ela saiu do eixo de assunto, e o classificador não a propõe mais — por isso nenhuma descrição a carrega. A linha continua no catálogo porque a chave estrangeira é SET NULL.",
                  }
            }
          />
        )}
      </div>
    </Disclosure>
  );
}


import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { createMacroCategory, updateMacroCategory, type DocumentSummary, type MacroCategory } from "@/api/client";
import { CATEGORY_DOCUMENTS_PAGE_SIZE, queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageBody } from "@/components/layout/PageBody";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { SidePanel, SidePanelClose } from "@/components/ui/SidePanel";
import { Tabs } from "@/components/ui/Tabs";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDate, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";
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
        <DescriptionPreview descriptionId={search.descricao} onClose={() => showPreview(undefined)} />
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
          <CategoryDocuments
            category={category}
            offset={offset}
            onPage={onPage}
            onPreview={onPreview}
          />
        )}
      </div>
    </Disclosure>
  );
}

/**
 * The descriptions inside one drawer, paged, read through the collection search.
 *
 * The read is ``GET /api/v1/documents`` with the same ``macro_category_id`` the list screen uses,
 * so the count on the card and the ``total`` here are one definition counted twice — the card's
 * `document_count` counts **distinct** descriptions through the same join
 * (``TagRepository._macro_category_query``), and
 * ``testing/integration/api/controller/test_category_documents.py`` fails when the two stop
 * agreeing.
 *
 * No new route was invented for this and none should be: the filter already existed, and a second
 * read of the same rows is the defect the taxonomy rule file names first.
 */
function CategoryDocuments({
  category,
  offset,
  onPage,
  onPreview,
}: {
  category: MacroCategory;
  offset: number;
  onPage: (offset: number) => void;
  onPreview: (descriptionId: string) => void;
}) {
  const documents = useQuery(
    queries.documents({
      macro_category_id: category.category_id,
      limit: CATEGORY_DOCUMENTS_PAGE_SIZE,
      offset,
    }),
  );

  const items = documents.data?.items ?? [];
  const total = documents.data?.total ?? 0;

  if (documents.error) return <ErrorState error={documents.error} />;
  if (documents.isPending) return <Spinner label="Lendo as descrições…" />;

  if (items.length === 0) {
    return category.is_active ? (
      <EmptyState
        title="Nenhuma descrição nesta categoria"
        hint="Nenhuma tag desta categoria está ligada a uma descrição ainda. As tags sem categoria de assunto estão na aba Classificar, em Tags."
      />
    ) : (
      <EmptyState
        title="Categoria aposentada e vazia"
        hint="Ela saiu do eixo de assunto, e o classificador não a propõe mais — por isso nenhuma descrição a carrega. A linha continua no catálogo porque a chave estrangeira é SET NULL."
      />
    );
  }

  return (
    <div className="grid gap-2">
      <ul className="divide-y divide-(--color-line)">
        {items.map((document) => (
          <li key={document.description_id}>
            <button
              type="button"
              onClick={() => onPreview(document.description_id)}
              className="flex w-full flex-col gap-1 px-1 py-2 text-left hover:bg-black/[0.03]"
            >
              <span className="flex items-start justify-between gap-3">
                <span className="min-w-0 text-sm font-medium">
                  {document.final_title || document.original_title}
                </span>
                <Badge tone={REVIEW_STATUS_TONE[document.review_status]}>
                  {REVIEW_STATUS_LABEL[document.review_status]}
                </Badge>
              </span>
              <span className="flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
                <span>{formatDate(document.document_date)}</span>
                {document.level ? <span>· {document.level}</span> : null}
                {document.typology ? <span>· {document.typology}</span> : null}
                {document.reference_code ? (
                  <code className="rounded bg-black/[0.05] px-1">{document.reference_code}</code>
                ) : null}
                {document.is_anomaly ? <Badge tone="warn">anomalia</Badge> : null}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {total > CATEGORY_DOCUMENTS_PAGE_SIZE ? (
        <div className="flex items-center justify-between pt-2 text-sm">
          <Button size="sm" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - CATEGORY_DOCUMENTS_PAGE_SIZE))}>
            ← Anterior
          </Button>
          <span className="text-xs text-(--color-muted)">
            {formatCount(offset + 1)}–{formatCount(Math.min(offset + CATEGORY_DOCUMENTS_PAGE_SIZE, total))} de{" "}
            {formatCount(total)}
          </span>
          <Button
            size="sm"
            disabled={offset + CATEGORY_DOCUMENTS_PAGE_SIZE >= total}
            onClick={() => onPage(offset + CATEGORY_DOCUMENTS_PAGE_SIZE)}
          >
            Próxima →
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The read-only preview: enough of the record to recognise it, and nothing that writes.
 *
 * It **reads the description again** instead of rendering the row the click came from. That is one
 * request, and it is what makes the panel honest against the URL: ``descricao`` can arrive from a
 * shared link, and the row it names may not be on the page the colleague's offset points at. A
 * panel that only worked when the list happened to carry the row would answer an empty box for a
 * link that is correct.
 *
 * The "Editar" goes to the dossier's **description** tab: the panel exists to recognise the record,
 * and the drawer of the tags is decided on the subject tab of the dossier — one click away there,
 * and not the question this panel was opened to answer.
 */
function DescriptionPreview({ descriptionId, onClose }: { descriptionId: string; onClose: () => void }) {
  const document = useQuery(queries.document(descriptionId));
  const title = document.data ? document.data.final_title || document.data.original_title : descriptionId;

  return (
    <SidePanel
      label={`Prévia de ${title}`}
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-(--color-muted)">Nada aqui escreve: o painel só mostra.</span>
          <Link
            to="/acervo/$descriptionId"
            params={{ descriptionId }}
            search={{ aba: "descricao" }}
            className="rounded bg-(--color-brand) px-3 py-1.5 text-sm font-medium text-white"
          >
            Editar
          </Link>
        </div>
      }
    >
      <div className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 text-base font-semibold">{title}</h2>
          <SidePanelClose onClose={onClose} />
        </div>

        {document.error ? <ErrorState error={document.error} /> : null}
        {document.isPending ? <Spinner label="Lendo a descrição…" /> : null}

        {document.data ? <DescriptionPreviewBody document={document.data} /> : null}
      </div>
    </SidePanel>
  );
}

/** The fields the panel shows, each one only when the description carries it. */
function DescriptionPreviewBody({ document }: { document: DocumentSummary }) {
  const tags = document.tags ?? [];

  return (
    <div className="grid gap-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={REVIEW_STATUS_TONE[document.review_status]}>
          {REVIEW_STATUS_LABEL[document.review_status]}
        </Badge>
        {document.is_published ? <Badge tone="ok">publicada</Badge> : <Badge tone="neutral">não publicada</Badge>}
        {document.is_anomaly ? <Badge tone="warn">anomalia</Badge> : null}
      </div>

      <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1 text-xs">
        {document.reference_code ? (
          <>
            <dt className="text-(--color-muted)">Código</dt>
            <dd>
              <code>{document.reference_code}</code>
            </dd>
          </>
        ) : null}
        <dt className="text-(--color-muted)">Data</dt>
        <dd>{formatDate(document.document_date)}</dd>
        <dt className="text-(--color-muted)">Nível</dt>
        <dd>{document.level ?? "—"}</dd>
        <dt className="text-(--color-muted)">Tipologia</dt>
        <dd>{document.typology ?? "—"}</dd>
        <dt className="text-(--color-muted)">Arranjo</dt>
        <dd className="break-all">{document.path ?? "—"}</dd>
      </dl>

      {document.scope_content ? (
        <p className="line-clamp-4 text-xs text-(--color-muted)">{document.scope_content}</p>
      ) : null}

      <div className="grid gap-1">
        <p className="text-xs font-medium text-(--color-muted)">Tags e categoria</p>
        {tags.length === 0 ? (
          <p className="text-xs text-(--color-muted)">Nenhuma tag nesta descrição.</p>
        ) : (
          <ul className="grid gap-1">
            {tags.map((tag) => (
              <li key={tag.tag_id} className="flex flex-wrap items-center gap-2 text-xs">
                <span className="truncate">{tag.name}</span>
                {tag.macro_category_name ? (
                  <Badge tone="accent">{tag.macro_category_name}</Badge>
                ) : (
                  <Badge tone="neutral" title="O classificador não arquivou esta tag numa categoria">
                    sem categoria
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

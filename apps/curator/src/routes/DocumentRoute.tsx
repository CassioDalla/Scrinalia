import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import type { DocumentDeletion, DocumentSummary, DocumentUpdateRequest } from "@/api/client";
import {
  curateTag,
  deleteDocument,
  fetchDocuments,
  linkEntity,
  linkTag,
  moveHierarchyNode,
  searchEntities,
  searchTags,
  unlinkEntity,
  unlinkTag,
  updateDocument,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { Typeahead } from "@/components/ui/Typeahead";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDate, formatDateTime, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";

const routeApi = getRouteApi("/acervo/$descriptionId");

const TAB_ITEMS = [
  { id: "descricao", label: "Descrição" },
  { id: "assuntos", label: "Assuntos" },
  { id: "arranjo", label: "Arranjo" },
  { id: "historico", label: "Histórico" },
];

/**
 * The dossier.
 *
 * The tabs are in the URL because each one is a shareable statement ("look at the subjects of this
 * one"), and the back button has to walk between them.
 */
export function DocumentRoute() {
  const { descriptionId } = routeApi.useParams();
  const { aba = "descricao" } = routeApi.useSearch();
  const navigate = routeApi.useNavigate();

  const document = useQuery(queries.document(descriptionId));

  return (
    <>
      <PageHeader
        title={
          document.data ? (
            document.data.final_title || document.data.original_title
          ) : (
            <span className="text-(--color-muted)">{descriptionId}</span>
          )
        }
        /*
          The badges are the *status* and not a subtitle: the dossier's heading is the record's own
          title, and the line under it reports what was read — the review state, whether it is
          published, whether the validator flagged it. `SCREENS.dossier` carries the flag that exempts
          this route from taking its heading from the catalogue, and the anatomy below is the same one
          every other screen has.
        */
        pending={document.isPending}
        status={
          document.data ? (
            <span className="flex flex-wrap items-center gap-2">
              <Badge tone={REVIEW_STATUS_TONE[document.data.review_status]}>
                {REVIEW_STATUS_LABEL[document.data.review_status]}
              </Badge>
              {document.data.is_published ? <Badge tone="ok">publicado</Badge> : null}
              {document.data.is_anomaly ? <Badge tone="warn">anomalia</Badge> : null}
              <span>{formatDate(document.data.document_date)}</span>
              {document.data.level ? <span>· {document.data.level}</span> : null}
            </span>
          ) : undefined
        }
        actions={
          <Link to="/acervo/lista" className="text-sm text-(--color-muted) hover:underline">
            ← voltar à lista
          </Link>
        }
      />

      <div className="px-6 pt-4">
        <Tabs
          items={TAB_ITEMS}
          active={aba}
          onChange={(id) =>
            navigate({ to: "/acervo/$descriptionId", params: { descriptionId }, search: { aba: id } })
          }
        />
      </div>

      <div className="px-6 py-5">
        {document.error ? <ErrorState error={document.error} /> : null}
        {document.isPending ? <Spinner /> : null}
        {document.data && aba === "descricao" ? (
          // ``key`` makes React remount the form when the dossier changes, which is what
          // resets the draft; syncing it from an effect would render twice on every navigation.
          <DescriptionTab key={document.data.description_id} document={document.data} />
        ) : null}
        {document.data && aba === "assuntos" ? <SubjectsTab document={document.data} /> : null}
        {document.data && aba === "arranjo" ? <ArrangementTab document={document.data} /> : null}
        {document.data && aba === "historico" ? <HistoryTab document={document.data} /> : null}
      </div>
    </>
  );
}

// ==========================================
// TAB: DESCRIÇÃO
// ==========================================

const ISAD_FIELDS: { name: keyof DocumentUpdateRequest; label: string; long?: boolean; date?: boolean }[] = [
  { name: "original_title", label: "Título original" },
  { name: "final_title", label: "Título final (decisão do arquivista)" },
  // A real date control: the field used to render the pt-BR display string ("1 de jan. de 1994") in
  // a box labelled AAAA-MM-DD, so editing it even once would send that text to a route that parses a
  // date. The ISO value is what the contract stores, so it is what the input holds.
  { name: "document_date", label: "Data do documento", date: true },
  { name: "reference_code", label: "Código de referência" },
  { name: "producers", label: "Produtor(es)" },
  { name: "scope_content", label: "Âmbito e conteúdo", long: true },
  { name: "provenance", label: "Procedência", long: true },
  { name: "admin_bio_history", label: "História administrativa / biografia", long: true },
  { name: "admin_archival_history", label: "História arquivística", long: true },
  { name: "language_name", label: "Idioma" },
  { name: "archivist_notes", label: "Notas do arquivista", long: true },
  { name: "access_conditions", label: "Condições de acesso (ISAD(G) 4.1)", long: true },
];

function DescriptionTab({ document }: { document: DocumentSummary }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [levels, setLevels] = useState<number | undefined>(document.level_id ?? undefined);
  const [typology, setTypology] = useState<number | undefined>(document.typology_id ?? undefined);
  const [published, setPublished] = useState(document.is_published);

  const levelOptions = useQuery(queries.levels());
  const typologyOptions = useQuery(queries.typologies());

  const save = useMutation({
    mutationFn: () => {
      const body: DocumentUpdateRequest = {
        ...(draft as DocumentUpdateRequest),
        level_id: levels ?? null,
        typology_id: typology ?? null,
        is_published: published,
        review_note: note || null,
      };
      return updateDocument(document.description_id, body);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
      setDraft({});
      setNote("");
    },
  });

  const valueOf = (name: keyof DocumentUpdateRequest): string => {
    if (name in draft) return draft[name] ?? "";
    const current = document[name as keyof DocumentSummary];
    if (current === null || current === undefined) return "";
    return String(current);
  };

  return (
    <div className="grid max-w-5xl gap-4">
      {/*
        The proposal is shown *next to* the field it proposes, and is never the stored value: the
        machine proposes the title, only the archivist writes ``final_title``.
      */}
      {document.suggested_final_title ? (
        <Card>
          <CardBody className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold tracking-wide text-(--color-muted) uppercase">Título sugerido</p>
              <p className="text-sm">{document.suggested_final_title}</p>
              <p className="text-xs text-(--color-muted)">
                Derivado na leitura a partir dos trechos aprovados; nunca armazenado.
              </p>
            </div>
            <Button
              onClick={() => setDraft((previous) => ({ ...previous, final_title: document.suggested_final_title ?? "" }))}
            >
              Usar esta
            </Button>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="text-sm font-semibold">ISAD(G)</CardHeader>
        <CardBody className="grid gap-3 sm:grid-cols-2">
          {ISAD_FIELDS.map((field) => (
            <label key={String(field.name)} className={field.long ? "sm:col-span-2" : ""}>
              <span className="mb-1 block text-xs font-medium text-(--color-muted)">{field.label}</span>
              {field.long ? (
                <Textarea
                  rows={3}
                  value={valueOf(field.name)}
                  onChange={(event) => setDraft((previous) => ({ ...previous, [field.name]: event.target.value }))}
                />
              ) : (
                <Input
                  type={field.date ? "date" : "text"}
                  value={valueOf(field.name)}
                  onChange={(event) => setDraft((previous) => ({ ...previous, [field.name]: event.target.value }))}
                />
              )}
            </label>
          ))}

          <label>
            <span className="mb-1 block text-xs font-medium text-(--color-muted)">Nível de descrição</span>
            <Select value={levels ?? ""} onChange={(event) => setLevels(event.target.value ? Number(event.target.value) : undefined)}>
              <option value="">— não classificado —</option>
              {levelOptions.data?.map((level) => (
                <option key={level.level_id} value={level.level_id}>
                  {level.name} ({formatCount(level.document_count)})
                </option>
              ))}
            </Select>
          </label>

          {/*
            The typology sits next to the level because it is the other closed catalogue a
            description is classified against — and the archivist is the one who can overrule the
            classifier. Only the active ones are offered: a retired typology is out of the
            classifier's candidate set, so it must be out of the editor's too.
          */}
          <label>
            <span className="mb-1 block text-xs font-medium text-(--color-muted)">
              Tipologia documental
            </span>
            <Select
              value={typology ?? ""}
              onChange={(event) => setTypology(event.target.value ? Number(event.target.value) : undefined)}
            >
              <option value="">— não classificada —</option>
              {typologyOptions.data?.map((option) => (
                <option key={option.typology_id} value={option.typology_id}>
                  {option.name} ({formatCount(option.document_count)})
                </option>
              ))}
            </Select>
          </label>

          <label className="flex items-center gap-2 pt-5">
            <input type="checkbox" checked={published} onChange={(event) => setPublished(event.target.checked)} />
            <span className="text-sm">
              Publicar na difusão
              <span className="block text-xs text-(--color-muted)">
                Eixo separado da revisão: publicar não bloqueia a IA de continuar melhorando o registro.
              </span>
            </span>
          </label>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="grid gap-3 sm:grid-cols-2">
          <label>
            <span className="mb-1 block text-xs font-medium text-(--color-muted)">Quem revisou</span>
            
          </label>
          <label>
            <span className="mb-1 block text-xs font-medium text-(--color-muted)">Motivo da edição</span>
            <Input value={note} onChange={(event) => setNote(event.target.value)} />
          </label>
          <div className="sm:col-span-2">
            <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Salvando…" : "Salvar e marcar como revisado"}
            </Button>
            <span className="ml-3 text-xs text-(--color-muted)">
              Toda edição registra antes/depois no histórico e marca o documento como revisado por humano —
              o que o retira da fila da IA.
            </span>
          </div>
          {save.error ? (
            <div className="sm:col-span-2">
              <ErrorState error={save.error} />
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

// ==========================================
// TAB: ASSUNTOS
// ==========================================

function SubjectsTab({ document }: { document: DocumentSummary }) {
  const queryClient = useQueryClient();
  const macroCategories = useQuery(queries.macroCategories());

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    // A reclassification changes the vocabulary, so every cached list of tags is stale too.
    void queryClient.invalidateQueries({ queryKey: ["taxonomy"] });
  };

  const removeTag = useMutation({
    mutationFn: (tagId: number) => unlinkTag(document.description_id, tagId),
    onSuccess: invalidate,
  });

  const removeEntity = useMutation({
    mutationFn: (entityId: number) => unlinkEntity(document.description_id, entityId),
    onSuccess: invalidate,
  });

  const addTag = useMutation({
    mutationFn: (tagId: number) => linkTag(document.description_id, tagId),
    onSuccess: invalidate,
  });

  const addEntity = useMutation({
    mutationFn: (entityId: number) => linkEntity(document.description_id, entityId),
    onSuccess: invalidate,
  });

  const reclassify = useMutation({
    mutationFn: ({ tagId, categoryId }: { tagId: number; categoryId: number | null }) =>
      curateTag(tagId, { macro_category_id: categoryId, note: null }),
    onSuccess: invalidate,
  });

  const tags = document.tags ?? [];
  const entities = document.entities ?? [];
  const drawers = macroCategories.data ?? [];

  return (
    <div className="grid max-w-5xl gap-4">
      <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
        Editar os assuntos marca o documento como <strong>revisado por humano</strong>, o que impede a IA de
        reescrevê-lo daqui em diante. É a mesma regra da edição de campos.
      </p>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <span className="text-sm font-semibold">Tags e assunto</span>
          <span className="text-xs text-(--color-muted)">
            {document.macro_categories?.length ?? 0} gaveta(s) votada(s)
          </span>
        </CardHeader>
        <CardBody className="grid gap-2">
          {tags.length === 0 ? (
            <EmptyState
              title="Nenhuma tag"
              hint="O worker de extração ainda não passou por esta descrição, ou ela não tem ponto de acesso."
            />
          ) : null}

          <ul className="divide-y divide-(--color-line)">
            {tags.map((tag) => (
              <li key={tag.tag_id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm">{tag.name}</span>
                  {tag.macro_category_name ? (
                    <Badge tone="accent" title={`Confiança da IA: ${tag.ai_confidence_score ?? "—"}`}>
                      {tag.macro_category_name}
                    </Badge>
                  ) : (
                    <Badge tone="neutral" title="O classificador não arquivou esta tag numa gaveta">
                      sem gaveta
                    </Badge>
                  )}
                  {tag.ai_confidence_score !== null && tag.ai_confidence_score !== undefined ? (
                    <span className="text-xs tabular-nums text-(--color-muted)">
                      {tag.ai_confidence_score.toFixed(2)}
                    </span>
                  ) : null}
                </span>
                <span className="flex items-center gap-2">
                  <Select
                    className="w-44"
                    aria-label={`Gaveta da tag ${tag.name}`}
                    value={tag.macro_category_id ?? ""}
                    disabled={reclassify.isPending}
                    title="Muda a gaveta desta tag em TODAS as descrições que a carregam, não só nesta."
                    onChange={(event) =>
                      reclassify.mutate({
                        tagId: tag.tag_id,
                        categoryId: event.target.value ? Number(event.target.value) : null,
                      })
                    }
                  >
                    <option value="">sem gaveta (não é assunto)</option>
                    {drawers.map((category) => (
                      <option key={category.category_id} value={category.category_id}>
                        {category.name}
                        {category.is_active ? "" : " (aposentada)"}
                      </option>
                    ))}
                  </Select>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={removeTag.isPending}
                    onClick={() => removeTag.mutate(tag.tag_id)}
                  >
                    {ACTION.remove.label}
                  </Button>
                </span>
              </li>
            ))}
          </ul>

          {reclassify.error ? <ErrorState error={reclassify.error} /> : null}
          {removeTag.error ? <ErrorState error={removeTag.error} /> : null}

          <div className="flex items-end gap-2 border-t border-(--color-line) pt-3">
            <label className="flex-1">
              <span className="mb-1 block text-xs font-medium text-(--color-muted)">
                Associar uma tag pelo nome
              </span>
              <Typeahead
                placeholder="digite ao menos 2 letras: igrej…"
                disabled={addTag.isPending}
                emptyLabel="nenhuma tag com esse trecho"
                onSearch={async (term) =>
                  (await searchTags(term)).map((result) => ({
                    value: String(result.tag_id),
                    label: result.name,
                    hint: `${formatCount(result.document_count)} doc${
                      result.macro_category_name ? ` · ${result.macro_category_name}` : " · sem gaveta"
                    }`,
                  }))
                }
                onPick={(option) => addTag.mutate(Number(option.value))}
              />
            </label>
          </div>
          <p className="text-xs text-(--color-muted)">
            A gaveta escolhida ao lado vale para <strong>todas</strong> as descrições que carregam a tag: é uma
            decisão sobre o vocabulário, não sobre este documento. O selo <em>sem gaveta</em> devolve a tag ao
            classificador.
          </p>
          {addTag.error ? <ErrorState error={addTag.error} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">Entidades nomeadas</CardHeader>
        <CardBody className="grid gap-2">
          {entities.length === 0 ? (
            <EmptyState title="Nenhuma entidade" hint="O extrator (NER) ainda não passou por esta descrição." />
          ) : null}
          <ul className="divide-y divide-(--color-line)">
            {entities.map((entity) => (
              <li key={entity.entity_id} className="flex items-center justify-between gap-3 py-2">
                <span className="flex items-center gap-2">
                  <span className="text-sm">{entity.name}</span>
                  <Badge tone="neutral">{entity.entity_type}</Badge>
                </span>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={removeEntity.isPending}
                  onClick={() => removeEntity.mutate(entity.entity_id)}
                >
                  {ACTION.remove.label}
                </Button>
              </li>
            ))}
          </ul>

          <div className="border-t border-(--color-line) pt-3">
            <span className="mb-1 block text-xs font-medium text-(--color-muted)">
              Associar uma entidade pelo nome
            </span>
            <Typeahead
              placeholder="digite ao menos 2 letras: igreja…"
              disabled={addEntity.isPending}
              emptyLabel="nenhuma entidade com esse trecho"
              onSearch={async (term) =>
                (await searchEntities(term)).map((result) => ({
                  value: String(result.entity_id),
                  label: result.name,
                  hint: `${result.entity_type} · ${formatCount(result.total_usage)} doc`,
                }))
              }
              onPick={(option) => addEntity.mutate(Number(option.value))}
            />
          </div>
          {addEntity.error ? <ErrorState error={addEntity.error} /> : null}
          {removeEntity.error ? <ErrorState error={removeEntity.error} /> : null}
        </CardBody>
      </Card>
    </div>
  );
}

// ==========================================
// TAB: ARRANJO
// ==========================================

function ArrangementTab({ document }: { document: DocumentSummary }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const levels = useQuery(queries.levels());

  // The route states where the node goes, so the screen always sends the parent it is showing:
  // ``null`` means "to the root" and there is no way to express "change only the level".
  const [parentId, setParentId] = useState<string | null>(document.parent_id ?? null);
  const [parentLabel, setParentLabel] = useState<string | null>(null);
  const [levelId, setLevelId] = useState<number | null>(document.level_id ?? null);
  const [note, setNote] = useState("");

  const move = useMutation({
    mutationFn: (newParentId: string | null) =>
      moveHierarchyNode(document.description_id, {
        new_parent_id: newParentId,
        level_id: levelId,
        note: note || null,
      }),
    onSuccess: (data) => {
      setParentId(data.parent_id ?? null);
      setParentLabel(null);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["hierarchy"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    },
  });

  const ancestors = document.ancestors ?? [];
  const parent = ancestors.length > 0 ? ancestors[ancestors.length - 1] : null;
  const currentParentTitle = parentLabel ?? parent?.title ?? parent?.description_id ?? null;

  return (
    <div className="grid max-w-5xl gap-4">
      <Card>
        <CardHeader className="text-sm font-semibold">Caminho até a raiz</CardHeader>
        <CardBody>
          {ancestors.length === 0 ? (
            <EmptyState
              title="Esta descrição está na raiz"
              hint="Com o arranjo ainda não materializado, quase todo o acervo está solto. A tela que resolve isso é o plano de arranjo."
              action={
                <Link to="/arranjo/plano">
                  <Button size="sm">Abrir o plano de arranjo</Button>
                </Link>
              }
            />
          ) : (
            <ol className="flex flex-wrap items-center gap-2 text-sm">
              {ancestors.map((ancestor) => (
                <li key={ancestor.description_id} className="flex items-center gap-2">
                  <Link
                    to="/acervo/$descriptionId"
                    params={{ descriptionId: ancestor.description_id }}
                    className="rounded bg-black/[0.04] px-2 py-0.5 hover:underline"
                  >
                    {ancestor.title ?? ancestor.description_id}
                  </Link>
                  <span className="text-(--color-muted)">›</span>
                </li>
              ))}
              <li className="font-medium">{document.final_title || document.original_title}</li>
            </ol>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">Unidade superior e nível</CardHeader>
        <CardBody className="grid gap-3">
          <p className="text-xs text-(--color-muted)">
            A API valida antes de escrever: um Item não pode ter filhos, um Dossiê não pode ficar sem pai, e
            mover para dentro da própria subárvore é recusado. A trilha da mudança fica no histórico desta
            descrição.
          </p>

          <div className="grid gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">
                Unidade superior atual: {currentParentTitle ?? "raiz"}
              </span>
              <Typeahead
                placeholder="buscar a nova unidade superior…"
                disabled={move.isPending}
                emptyLabel="nenhuma descrição com esse trecho"
                onSearch={async (term) => {
                  const page = await fetchDocuments({ term, limit: 8 });
                  return page.items
                    .filter((item) => item.description_id !== document.description_id)
                    .map((item) => ({
                      value: item.description_id,
                      label: item.final_title || item.original_title,
                      hint: item.level ?? item.description_id,
                    }));
                }}
                onPick={(option) => {
                  setParentId(option.value);
                  setParentLabel(option.label);
                }}
              />
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">Nível de descrição</span>
              <Select
                value={levelId ?? ""}
                onChange={(event) => setLevelId(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">— manter —</option>
                {(levels.data ?? []).map((level) => (
                  <option key={level.level_id} value={level.level_id}>
                    {level.ordinal}. {level.name}
                  </option>
                ))}
              </Select>
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">Quem decide (texto livre até existir auth)</span>
              
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">Nota da decisão</span>
              <Input value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" disabled={move.isPending} onClick={() => move.mutate(parentId)}>
              {move.isPending ? "Movendo…" : "Mover para esta unidade"}
            </Button>
            <Button
              disabled={move.isPending || parentId === null}
              title="Deixa a descrição na raiz. O nível continua o que estiver escolhido acima."
              onClick={() => move.mutate(null)}
            >
              Promover à raiz
            </Button>
            <Button
              variant="ghost"
              disabled={move.isPending}
              onClick={() => navigate({ to: "/arranjo/diagnostico", search: { issue: "LEVEL_DEPTH_MISMATCH" } })}
            >
              ver incoerências de nível
            </Button>
          </div>

          {move.error ? <ErrorState error={move.error} /> : null}
          {move.data ? (
            <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/25">
              Movido: agora pende de {move.data.parent_id ?? "ninguém (raiz)"} e o caminho é{" "}
              <code>{move.data.path}</code>.
            </p>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">Filhos</CardHeader>
        <CardBody className="text-sm">
          {document.children_count === 0 ? (
            <p className="text-(--color-muted)">Nenhuma descrição pende diretamente desta.</p>
          ) : (
            <p>
              <strong>{formatCount(document.children_count)}</strong> descrição(ões) diretamente abaixo. Mover esta
              unidade leva a subárvore inteira: o caminho é reescrito em uma instrução.
            </p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">Publicação</CardHeader>
        <CardBody className="text-sm">
          {document.is_published ? (
            <Badge tone="ok">publicado na difusão</Badge>
          ) : (
            <Badge tone="neutral">não publicado</Badge>
          )}
          <p className="mt-2 text-xs text-(--color-muted)">
            Publicar é uma decisão de difusão, separada da revisão. O campo está na aba Descrição.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

// ==========================================
// TAB: HISTÓRICO
// ==========================================

function HistoryTab({ document }: { document: DocumentSummary }) {
  const descriptionId = document.description_id;
  const { data, isPending, error } = useQuery(queries.revisions(descriptionId));

  if (error) return <ErrorState error={error} />;
  if (isPending) return <Spinner />;

  return (
    <div className="grid max-w-4xl gap-4">
      {!data || data.length === 0 ? (
        <EmptyState
          title="Nenhuma revisão humana"
          hint="O histórico é o que dá crédito ao selo de revisado: ele registra quem mudou o quê, de qual valor para qual, e por quê."
        />
      ) : (
        <ol className="space-y-3">
          {data.map((revision) => (
        <li key={revision.revision_id}>
          <Card>
            <CardHeader className="flex items-center justify-between text-sm">
              <span className="font-medium">{revision.changed_by ?? "autoria não registrada"}</span>
              <span className="text-xs text-(--color-muted)">{formatDateTime(revision.created_at)}</span>
            </CardHeader>
            <CardBody className="space-y-2">
              {revision.note ? <p className="text-sm italic text-(--color-muted)">{revision.note}</p> : null}
              <ul className="space-y-1">
                {Object.entries(revision.changes ?? {}).map(([field, change]) => {
                  const pair = change as { old?: unknown; new?: unknown };
                  return (
                    <li key={field} className="text-xs">
                      <code className="rounded bg-black/[0.05] px-1 font-medium">{field}</code>
                      <span className="mx-2 text-(--color-danger) line-through">
                        {JSON.stringify(pair?.old) ?? "—"}
                      </span>
                      <span className="text-(--color-ok)">{JSON.stringify(pair?.new) ?? "—"}</span>
                    </li>
                  );
                })}
              </ul>
            </CardBody>
          </Card>
          </li>
        ))}
        </ol>
      )}

      {/*
        The deletion lives here, at the end of the record's history, and not in the page header.
        Two reasons, and both are about the cost of a misclick: the header sits next to navigation
        ("voltar à lista"), and this is the one action in the curator UI that removes a record for
        good. The confirmation asks for the reference code — the same field the archivist reads to
        identify the description — so the click cannot be a reflex.
      */}
      <DeleteDocumentCard document={document} />
    </div>
  );
}

/**
 * The confirmation step of the deletion, and the only place its consequences are stated.
 *
 * The typed reference code is not decoration: it is the difference between "excluir" and "excluir
 * *esta* descrição", and it is the same guard the API's children check cannot provide (the API cannot
 * know whether the archivist meant this row).
 */
function DeleteDocumentCard({ document }: { document: DocumentSummary }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [note, setNote] = useState("");
  const [done, setDone] = useState<DocumentDeletion | null>(null);

  // The reference code is what a person recognises; a description without one is confirmed by its id,
  // which the screen shows next to the field so there is something to copy.
  const expected = document.reference_code ?? document.description_id;
  const matches = confirmation.trim() === expected;

  const remove = useMutation({
    mutationFn: () =>
      deleteDocument(document.description_id, { note: note || null }),
    onSuccess: (response) => {
      setDone(response.data);
      // The detail query is *removed*, not invalidated: invalidating it would refetch a document that
      // no longer exists and paint a 404 in the console of a page the archivist is leaving.
      queryClient.removeQueries({ queryKey: ["documents", "detail", document.description_id] });
      queryClient.removeQueries({ queryKey: ["documents", "revisions", document.description_id] });
      void queryClient.invalidateQueries({ queryKey: ["documents", "search"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["documents", "deletions"] });
      // The record is gone, so the trail is the only place it still exists — and the archivist has
      // just made it. Landing there shows the entry instead of a list where something vanished.
      void navigate({ to: "/acervo/excluidas" });
    },
  });

  return (
    <Card className="ring-(--color-danger)/30">
      <CardBody className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="grid gap-1">
            <p className="text-sm font-semibold text-(--color-danger)">Excluir esta descrição</p>
            <p className="text-xs text-(--color-muted)">
              Exclusão definitiva. O retrato da descrição fica na trilha de exclusões; nada a traz de volta.
            </p>
          </div>
          <Button size="sm" variant="danger" onClick={() => setOpen((current) => !current)}>
            {open ? ACTION.cancel.label : "Excluir descrição…"}
          </Button>
        </div>

        {open ? (
          <div className="grid gap-3 rounded-md bg-(--color-danger)/5 p-3 ring-1 ring-(--color-danger)/20">
            <p className="text-xs text-(--color-danger)">
              Uma descrição com filhos <strong>não pode</strong> ser excluída: a árvore ficaria apontando para um
              ramo que não existe. O serviço recusa e diz quantos filhos estão no caminho.
            </p>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">
                Escreva <code>{expected}</code> para confirmar
              </span>
              <Input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder={expected}
                className="max-w-md font-mono"
              />
            </label>

            {/*
              One field, and it used to be two: the other was a label for a "who deletes" input that
              no longer exists — the API takes the actor from the session since ADR 0009 — so the form
              showed a field title with nothing under it.
            */}
            <div className="grid gap-2">
              <label className="flex flex-col gap-1 text-xs">
                <span className="text-(--color-muted)">Motivo (guardado na trilha)</span>
                <Input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="ex.: duplicata da descrição 00574"
                />
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="danger"
                disabled={!matches || remove.isPending}
                title={matches ? undefined : "O código precisa bater com o da descrição."}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? ACTION.exclude.pending : "Excluir definitivamente"}
              </Button>
              <span className="text-xs text-(--color-muted)">
                {matches ? "o código confere" : "o botão libera quando o código bater"}
              </span>
            </div>

            {remove.error ? <ErrorState error={remove.error} /> : null}
            {done ? (
              <p className="text-xs text-(--color-ok)">
                “{done.title}” foi excluída. A trilha guarda o retrato dela.
              </p>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

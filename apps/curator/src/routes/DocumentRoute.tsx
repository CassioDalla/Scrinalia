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
import { IsadFieldControl } from "@/components/description/IsadFieldControl";
import { DocumentThumbnail } from "@/components/description/Thumbnail";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { Typeahead } from "@/components/ui/Typeahead";
import { ACTION, DIGITAL_OBJECT } from "@/lib/copy";
import { ENTITY_ORIGIN_HINT, ENTITY_ORIGIN_LABEL, ENTITY_ORIGIN_TONE } from "@/lib/entities";
import { formatCount, formatDate, formatDateTime, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";
import { fieldsOfArea, ISAD_AREAS } from "@/lib/isad";

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
            ← Voltar à lista
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

function DescriptionTab({ document }: { document: DocumentSummary }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [levels, setLevels] = useState<number | undefined>(document.level_id ?? undefined);
  const [typology, setTypology] = useState<number | undefined>(document.typology_id ?? undefined);
  const [published, setPublished] = useState(document.is_published);

  const levelOptions = useQuery(queries.levels());
  const typologyOptions = useQuery(queries.typologies());
  const languageOptions = useQuery(queries.languages());

  const save = useMutation({
    mutationFn: () => {
      // An empty string is not a value the archive stores: it is the archivist deleting what was
      // there, and sending it to a field typed as a date was a 422. Every cleared control travels
      // as ``null``, which is how the contract says "nada".
      const edited: Record<string, string | null> = {};
      for (const [name, value] of Object.entries(draft)) {
        edited[name] = value === "" ? null : value;
      }
      const body: DocumentUpdateRequest = {
        ...(edited as DocumentUpdateRequest),
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

  const setField = (name: string, value: string) => {
    setDraft((previous) => ({ ...previous, [name]: value }));
  };

  return (
    <div className="grid gap-4">
      {/*
        The miniature comes from the API, not from the bucket: ``thumbnail_url`` is derived on the
        server from the stored URI, so this screen never assembles a path and never sees S3. The
        placeholder is not an edge case — four descriptions of the reference collection have no
        source image at all — and the "indisponível" state covers an object that left the bucket.
      */}
      <Card>
        <CardHeader className="text-sm font-semibold">Imagem</CardHeader>
        <CardBody>
          <DocumentThumbnail
            url={document.thumbnail_url}
            title={document.final_title || document.original_title}
            variant="dossier"
          />
        </CardBody>
      </Card>

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
                Título proposto sem a parte fixa já aprovada. Só entra no registro se você usar.
              </p>
            </div>
            <Button
              onClick={() => setDraft((previous) => ({ ...previous, final_title: document.suggested_final_title ?? "" }))}
            >
              Usar este título
            </Button>
          </CardBody>
        </Card>
      ) : null}

      {/*
        The record in the norm's own areas: the archivist learned ISAD(G) as 3.1 to 3.7, and a flat
        list of thirty controls in alphabetical order is a list nobody can check against a ficha.
      */}
      {ISAD_AREAS.map((area) => (
        <Card key={area.id}>
          <CardHeader className="text-sm font-semibold">{area.title}</CardHeader>
          <CardBody className="grid gap-3 sm:grid-cols-2">
            <p className="text-xs text-(--color-muted) sm:col-span-2">{area.hint}</p>

            {area.id === "identity" ? (
              <>
                <Field label="Título Original" hint="O título que a origem declarou.">
                  <Input value={valueOf("original_title")} onChange={(event) => setField("original_title", event.target.value)} />
                </Field>
                <Field
                  label="Título Final (Decisão do Arquivista)"
                  hint="O título que você aprova. Enquanto estiver vazio, vale o título original."
                >
                  <Input value={valueOf("final_title")} onChange={(event) => setField("final_title", event.target.value)} />
                </Field>
                <Field label="Nível de Descrição">
                  <Select
                    value={levels ?? ""}
                    onChange={(event) => setLevels(event.target.value ? Number(event.target.value) : undefined)}
                  >
                    <option value="">— não classificado —</option>
                    {levelOptions.data?.map((level) => (
                      <option key={level.level_id} value={level.level_id}>
                        {level.name} ({formatCount(level.document_count)})
                      </option>
                    ))}
                  </Select>
                </Field>
                {/*
                  The typology sits next to the level because it is the other closed catalogue a
                  description is classified against — and the archivist is the one who can overrule
                  the classifier. Only the active ones are offered: a retired typology is out of the
                  classifier's candidate set, so it must be out of the editor's too.
                */}
                <Field label="Tipologia Documental">
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
                </Field>
              </>
            ) : null}

            {fieldsOfArea(area.id).map((field) => (
              <IsadFieldControl
                key={field.name}
                field={field}
                value={valueOf(field.name)}
                languages={languageOptions.data ?? []}
                onChange={(value) => setField(field.name, value)}
                dateAs="iso"
                hint={
                  field.name === "document_date" && document.date_expression
                    ? `Como está escrito na fonte: “${document.date_expression}”.`
                    : undefined
                }
              />
            ))}

            {area.id === "identity" ? <ParentReference document={document} /> : null}

            {area.id === "context" && document.original_url ? (
              <div className="grid gap-1 text-xs sm:col-span-2">
                <span className="text-(--color-muted)">Fonte</span>
                <a
                  className="truncate text-sm underline"
                  href={document.original_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {document.original_url}
                </a>
                <span className="text-(--color-muted)">
                  A página de onde este registro foi lido — não o objeto digital, que ainda não é guardado.
                </span>
              </div>
            ) : null}
          </CardBody>
        </Card>
      ))}

      <Card>
        <CardHeader className="text-sm font-semibold">Difusão</CardHeader>
        <CardBody>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={published} onChange={(event) => setPublished(event.target.checked)} />
            <span className="text-sm">
              Publicar na difusão
              <span className="block text-xs text-(--color-muted)">
                Publicar é decisão de difusão, separada da revisão: publicar não impede a IA de continuar melhorando
                o registro.
              </span>
            </span>
          </label>
        </CardBody>
      </Card>

      {/*
        The control is disabled on purpose, and the sentence that explains it is one definition
        (``copy.ts``) shared with the manual entry form: #198 owns the digital object, and until it
        lands the archive keeps the description and not the file.
      */}
      <Card>
        <CardHeader className="text-sm font-semibold">{DIGITAL_OBJECT.label}</CardHeader>
        <CardBody className="grid gap-2">
          <input
            type="file"
            disabled
            aria-label={DIGITAL_OBJECT.label}
            title={DIGITAL_OBJECT.disabled}
            className="text-sm text-(--color-muted)"
          />
          <p className="text-xs text-(--color-muted)">{DIGITAL_OBJECT.hint}</p>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="grid gap-3 sm:grid-cols-2">
          <Field label="Motivo da Edição">
            <Input value={note} onChange={(event) => setNote(event.target.value)} />
          </Field>
          <div className="sm:col-span-2">
            <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Salvando…" : "Salvar e marcar como revisado"}
            </Button>
            <span className="ml-3 text-xs text-(--color-muted)">
              Toda edição fica no histórico e marca o documento como revisado por humano; a partir daí a IA não o
              reescreve.
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

/**
 * Where the description sits, and what the origin declared when that is not resolvable yet.
 *
 * The pending parent is not an error: the origin is allowed to deliver the child first, and the
 * transfer marks it while the code waits. The link itself is made in the arrangement tab.
 */
function ParentReference({ document }: { document: DocumentSummary }) {
  // The parent is the last rung of the branch the read view already carries, so the line can name
  // it even when the origin declared no code. A raw ``description_id`` is the last resort: it is
  // what the archive knows when the arrangement has a parent the reader cannot resolve.
  const branch = (document.ancestors ?? []).at(-1);
  const parentLabel = branch?.title ?? document.parent_reference_code ?? "unidade superior";

  return (
    <div className="grid gap-1 text-xs sm:col-span-2">
      <span className="text-(--color-muted)">Unidade Superior</span>
      {document.parent_id ? (
        <Link
          to="/acervo/$descriptionId"
          params={{ descriptionId: document.parent_id }}
          className="text-sm underline"
        >
          {parentLabel}
        </Link>
      ) : document.parent_reference_code ? (
        <span className="text-sm">
          {document.parent_reference_code} — declarada pela origem, aguardando a descrição da unidade superior. O
          vínculo se faz na aba Arranjo.
        </span>
      ) : (
        <span className="text-sm text-(--color-muted)">Não declarada. O vínculo se faz na aba Arranjo.</span>
      )}
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
    <div className="grid gap-4">
      <Notice tone="warn">
        Editar os assuntos marca o documento como <strong>revisado por humano</strong>, o que impede a IA de
        reescrevê-lo daqui em diante. É a mesma regra da edição de campos.
      </Notice>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <span className="text-sm font-semibold">Tags e categorias</span>
          <span className="text-xs text-(--color-muted)">
            Categorias atribuídas: {document.macro_categories?.length ?? 0}
          </span>
        </CardHeader>
        <CardBody className="grid gap-2">
          {tags.length === 0 ? (
            <EmptyState
              title="Nenhuma tag"
              hint="A extração automática ainda não passou por esta descrição, ou ela não tem ponto de acesso."
            />
          ) : null}

          <ul className="divide-y divide-(--color-line)">
            {tags.map((tag) => (
              <li key={tag.tag_id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm">{tag.name}</span>
                  {tag.macro_category_name ? (
                    <Badge tone="accent" title={`Confiança da classificação: ${tag.ai_confidence_score ?? "—"}`}>
                      {tag.macro_category_name}
                    </Badge>
                  ) : (
                    <Badge tone="neutral" title="Esta tag não está em nenhuma categoria de assunto.">
                      sem categoria
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
                    aria-label={`Categoria da tag ${tag.name}`}
                    value={tag.macro_category_id ?? ""}
                    disabled={reclassify.isPending}
                    title="Vale para todas as descrições que carregam a tag, não só para esta."
                    onChange={(event) =>
                      reclassify.mutate({
                        tagId: tag.tag_id,
                        categoryId: event.target.value ? Number(event.target.value) : null,
                      })
                    }
                  >
                    <option value="">sem categoria (não é assunto)</option>
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
                Associe uma tag pelo nome
              </span>
              <Typeahead
                placeholder="digite ao menos 2 letras: igrej…"
                disabled={addTag.isPending}
                emptyLabel="Nenhuma tag com esse trecho"
                onSearch={async (term) =>
                  (await searchTags(term)).map((result) => ({
                    value: String(result.tag_id),
                    label: result.name,
                    hint: `${formatCount(result.document_count)} doc${
                      result.macro_category_name ? ` · ${result.macro_category_name}` : " · sem categoria"
                    }`,
                  }))
                }
                onPick={(option) => addTag.mutate(Number(option.value))}
              />
            </label>
          </div>
          <p className="text-xs text-(--color-muted)">
            A categoria escolhida ao lado vale para <strong>todas</strong> as descrições que carregam a tag: é uma
            decisão sobre o vocabulário, não sobre esta descrição. <em>Sem categoria</em> declara que a tag não é
            assunto, e a grafia não volta a virar tag.
          </p>
          {addTag.error ? <ErrorState error={addTag.error} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">Entidades nomeadas</CardHeader>
        <CardBody className="grid gap-2">
          {entities.length === 0 ? (
            <EmptyState title="Nenhuma entidade" hint="A extração automática de nomes ainda não passou por esta descrição." />
          ) : null}
          <ul className="divide-y divide-(--color-line)">
            {entities.map((entity) => (
              <li key={entity.entity_id} className="flex items-center justify-between gap-3 py-2">
                <span className="flex items-center gap-2">
                  <span className="text-sm">{entity.name}</span>
                  <Badge tone="neutral">{entity.entity_type}</Badge>
                  <Badge tone={ENTITY_ORIGIN_TONE[entity.origin]} title={ENTITY_ORIGIN_HINT[entity.origin]}>
                    {ENTITY_ORIGIN_LABEL[entity.origin]}
                  </Badge>
                </span>
                <span className="flex items-center gap-1.5">
                  {entity.origin === "HUMAN" ? null : (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={addEntity.isPending}
                      title="Registra que você revisou esta entidade: a IA não a remove depois."
                      onClick={() => addEntity.mutate(entity.entity_id)}
                    >
                      {ACTION.confirm.label}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={removeEntity.isPending}
                    onClick={() => removeEntity.mutate(entity.entity_id)}
                  >
                    {ACTION.remove.label}
                  </Button>
                </span>
              </li>
            ))}
          </ul>

          <div className="border-t border-(--color-line) pt-3">
            <span className="mb-1 block text-xs font-medium text-(--color-muted)">
              Associe uma entidade pelo nome
            </span>
            <Typeahead
              placeholder="digite ao menos 2 letras: igreja…"
              disabled={addEntity.isPending}
              emptyLabel="Nenhuma entidade com esse trecho"
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
    <div className="grid gap-4">
      <Card>
        <CardHeader className="text-sm font-semibold">Caminho até a raiz</CardHeader>
        <CardBody>
          {ancestors.length === 0 ? (
            <EmptyState
              title="Esta descrição está na raiz"
              hint="Enquanto o arranjo não estiver definido, quase todo o acervo fica solto. O plano de arranjo é a tela que resolve isso."
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
            A mudança é conferida antes de ser gravada: um Item não pode receber filhos, um Dossiê não pode ficar
            sem unidade superior, e mover uma unidade para dentro dela mesma é recusado. O resultado fica no
            histórico desta descrição.
          </p>

          <div className="grid gap-2 sm:grid-cols-2">
            <Field label={<>Unidade Superior Atual: {currentParentTitle ?? "raiz"}</>}>
              <Typeahead
                placeholder="buscar a nova unidade superior…"
                disabled={move.isPending}
                emptyLabel="Nenhuma descrição com esse trecho"
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
            </Field>

            <Field label="Nível de Descrição">
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
            </Field>

            {/*
              One field, and it used to be two: the other was a label for a "who decides" input that
              no longer exists — the API takes the actor from the session since ADR 0009 — so the form
              showed a field title with nothing under it.
            */}
            <Field label="Nota da Decisão">
              <Input value={note} onChange={(event) => setNote(event.target.value)} />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" disabled={move.isPending} onClick={() => move.mutate(parentId)}>
              {move.isPending ? "Movendo…" : "Mover para esta unidade"}
            </Button>
            <Button
              disabled={move.isPending || parentId === null}
              title="Coloca a descrição na raiz. O nível escolhido acima continua valendo."
              onClick={() => move.mutate(null)}
            >
              Promover à raiz
            </Button>
            <Button
              variant="ghost"
              disabled={move.isPending}
              onClick={() => navigate({ to: "/arranjo/diagnostico", search: { issue: "LEVEL_DEPTH_MISMATCH" } })}
            >
              Ver incoerências de nível
            </Button>
          </div>

          {move.error ? <ErrorState error={move.error} /> : null}
          {move.data ? (
            <Notice tone="ok">
              Movido. A unidade superior agora é {move.data.parent_id ?? "a raiz"}, e o caminho no arranjo é{" "}
              <code>{move.data.path}</code>.
            </Notice>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">Filhos</CardHeader>
        <CardBody className="text-sm">
          {document.children_count === 0 ? (
            <p className="text-(--color-muted)">Nenhuma descrição está diretamente abaixo desta.</p>
          ) : (
            <p>
              Descrições diretamente abaixo: <strong>{formatCount(document.children_count)}</strong>. Mover esta
              unidade leva a subárvore inteira junto.
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
    <div className="grid gap-4">
      {!data || data.length === 0 ? (
        <EmptyState
          title="Nenhuma revisão humana"
          hint="O histórico registra quem mudou o quê, de qual valor para qual, e por quê."
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
              Exclusão definitiva. O Histórico de exclusões guarda os dados da descrição; nada a traz de volta.
            </p>
          </div>
          <Button size="sm" variant="danger" onClick={() => setOpen((current) => !current)}>
            {open ? ACTION.cancel.label : "Excluir descrição…"}
          </Button>
        </div>

        {open ? (
          <Notice tone="danger" as="div" className="grid gap-3">
            <p className="text-xs text-(--color-danger)">
              Uma descrição com filhos <strong>não pode</strong> ser excluída: a árvore ficaria apontando para um
              ramo que não existe. Exclua ou mova as descrições abaixo primeiro.
            </p>

            <Field label={<>Escreva <code>{expected}</code> para confirmar</>}>
              <Input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder={expected}
                className="max-w-md font-mono"
              />
            </Field>

            {/*
              One field, and it used to be two: the other was a label for a "who deletes" input that
              no longer exists — the API takes the actor from the session since ADR 0009 — so the form
              showed a field title with nothing under it.
            */}
            <div className="grid gap-2">
              <Field label="Motivo da Exclusão">
                <Input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="ex.: duplicata da descrição 00574"
                />
              </Field>
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
                “{done.title}” foi excluída. O Histórico de exclusões guarda os dados dela.
              </p>
            ) : null}
          </Notice>
        ) : null}
      </CardBody>
    </Card>
  );
}

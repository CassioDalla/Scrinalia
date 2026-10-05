import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link } from "@tanstack/react-router";
import { useState } from "react";

import type { DocumentSummary, DocumentUpdateRequest } from "@/api/client";
import { linkTag, unlinkEntity, unlinkTag, updateDocument } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
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
        subtitle={
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
          ) : null
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
        {document.data && aba === "historico" ? <HistoryTab descriptionId={descriptionId} /> : null}
      </div>
    </>
  );
}

// ==========================================
// TAB: DESCRIÇÃO
// ==========================================

const ISAD_FIELDS: { name: keyof DocumentUpdateRequest; label: string; long?: boolean }[] = [
  { name: "original_title", label: "Título original" },
  { name: "final_title", label: "Título final (decisão do arquivista)" },
  { name: "document_date", label: "Data do documento (AAAA-MM-DD)" },
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
  const [changedBy, setChangedBy] = useState("");
  const [note, setNote] = useState("");
  const [levels, setLevels] = useState<number | undefined>(document.level_id ?? undefined);
  const [published, setPublished] = useState(document.is_published);

  const levelOptions = useQuery(queries.levels());

  const save = useMutation({
    mutationFn: () => {
      const body: DocumentUpdateRequest = {
        ...(draft as DocumentUpdateRequest),
        level_id: levels ?? null,
        is_published: published,
        changed_by: changedBy || null,
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
    if (name === "document_date") return formatDate(String(current)).replace(/^sem data$/, "");
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
            <Input value={changedBy} onChange={(event) => setChangedBy(event.target.value)} placeholder="nome" />
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
  const [newTagId, setNewTagId] = useState("");

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
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
    onSuccess: () => {
      setNewTagId("");
      invalidate();
    },
  });

  const tags = document.tags ?? [];
  const entities = document.entities ?? [];

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
              <li key={tag.tag_id} className="flex items-center justify-between gap-3 py-2">
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
                <Button
                  size="sm"
                  variant="danger"
                  disabled={removeTag.isPending}
                  onClick={() => removeTag.mutate(tag.tag_id)}
                >
                  remover
                </Button>
              </li>
            ))}
          </ul>

          <div className="flex items-end gap-2 border-t border-(--color-line) pt-3">
            <label className="flex-1">
              <span className="mb-1 block text-xs font-medium text-(--color-muted)">
                Associar tag pelo id (o vocabulário completo está em /assuntos/tags)
              </span>
              <Input
                value={newTagId}
                inputMode="numeric"
                placeholder="ex.: 42"
                onChange={(event) => setNewTagId(event.target.value)}
              />
            </label>
            <Button
              variant="primary"
              disabled={!newTagId || addTag.isPending}
              onClick={() => addTag.mutate(Number(newTagId))}
            >
              Associar
            </Button>
          </div>
          {addTag.error ? <ErrorState error={addTag.error} /> : null}
          {removeTag.error ? <ErrorState error={removeTag.error} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">Entidades nomeadas</CardHeader>
        <CardBody>
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
                  remover
                </Button>
              </li>
            ))}
          </ul>
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
  const ancestors = document.ancestors ?? [];

  return (
    <div className="grid max-w-5xl gap-4">
      <Card>
        <CardHeader className="text-sm font-semibold">Caminho até a raiz</CardHeader>
        <CardBody>
          {ancestors.length === 0 ? (
            <EmptyState
              title="Esta descrição está na raiz"
              hint="Com o arranjo ainda não materializado, todas as 3.608 descrições estão soltas. A tela que resolve isso é o plano de arranjo."
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
        <CardHeader className="text-sm font-semibold">Filhos</CardHeader>
        <CardBody className="text-sm">
          {document.children_count === 0 ? (
            <p className="text-(--color-muted)">Nenhuma descrição pende diretamente desta.</p>
          ) : (
            <p>
              <strong>{formatCount(document.children_count)}</strong> descrição(ões) diretamente abaixo.
            </p>
          )}
          <p className="mt-3 text-xs text-(--color-muted)">
            Mover um ramo e trocar a unidade superior chegam na onda 2 do plano, junto com a tela de arranjo:
            a API já valida, mas a decisão estrutural é tomada lá, não aqui.
          </p>
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

function HistoryTab({ descriptionId }: { descriptionId: string }) {
  const { data, isPending, error } = useQuery(queries.revisions(descriptionId));

  if (error) return <ErrorState error={error} />;
  if (isPending) return <Spinner />;
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="Nenhuma revisão humana"
        hint="O histórico é o que dá crédito ao selo de revisado: ele registra quem mudou o quê, de qual valor para qual, e por quê."
      />
    );
  }

  return (
    <ol className="max-w-4xl space-y-3">
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
  );
}

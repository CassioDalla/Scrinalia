import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  createTextTemplate,
  deleteTextTemplate,
  previewTextTemplate,
  suggestTextTemplates,
  updateTextTemplate,
  type TemplateAction,
  type TemplateDryRunResponse,
  type TemplateScope,
  type TemplateStatus,
  type TextTemplate,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { ACTION } from "@/lib/copy";
import { formatCount } from "@/lib/format";
import {
  TEMPLATE_ACTION_LABEL,
  TEMPLATE_SCOPE_HINT,
  TEMPLATE_SCOPE_LABEL,
  TEMPLATE_STATUS_LABEL,
  TEMPLATE_STATUS_TONE,
} from "@/lib/quality";
import { labelOf } from "@/lib/hierarchy";
import { asEnum } from "@/lib/search";
import { routeMessage } from "@/lib/messages";

const routeApi = getRouteApi("/qualidade/trechos");

export type TextTemplatesSearch = { status?: TemplateStatus };

/** The vocabulary the route accepts, read from the labels the screen already owns. */
const TEMPLATE_STATUSES = Object.keys(TEMPLATE_STATUS_LABEL) as TemplateStatus[];

export function validateTextTemplatesSearch(search: Record<string, unknown>): TextTemplatesSearch {
  return { status: asEnum(search.status, TEMPLATE_STATUSES) };
}

const SCOPES: TemplateScope[] = ["EMBEDDING", "NER", "TITLE"];

/**
 * The catalog of repeated excerpts.
 *
 * This is the largest measured gain of the project: **53% of the collection shared the same
 * ``scope_content`` block** and 2,467 documents carried the same title prefix, which dominated the
 * embeddings and degraded the search.
 *
 * The screen exists for one decision — the ``scope`` — and it must not offer a shortcut around it.
 * Approving everything the machine suggested **worsened** the ranking (Hit@10 0.562 → 0.500): the
 * title prefix helped the derived title and hurt the vector, which is exactly why a block is dropped
 * from the consumers it damages and kept where it helps. Hence no "aprovar todos" button anywhere.
 */
export function TextTemplatesRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [minRatio, setMinRatio] = useState(0.05);
  const [minDocuments, setMinDocuments] = useState(5);

  const templates = useQuery(queries.textTemplates(search.status));
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["quality", "text-templates"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const suggest = useMutation({
    mutationFn: () => suggestTextTemplates({ min_ratio: minRatio, min_documents: minDocuments }),
    onSuccess: invalidate,
  });

  const rows = templates.data ?? [];

  return (
    <>
      <PageHeader
        screen="textTemplates"
        pending={templates.isPending}
        status={
          templates.data
            ? rows.length === 0
              ? "Nenhum trecho no filtro atual"
              : `${formatCount(rows.length)} trechos no filtro atual`
            : undefined
        }
      />

      <PageBody>
        <Notice tone="accent">
          <strong>O escopo é a decisão que importa.</strong> Cada trecho diz de qual consumidor ele sai
          — vetor, extração de nomes ou título sugerido. Aprovar tudo o que a máquina sugeriu
          <strong> piorou</strong> o ranking (Hit@10 0.562 → 0.500): o prefixo de título ajudava o
          título e prejudicava o vetor. Por isso não existe botão de aprovar todos aqui.
        </Notice>

        <Disclosure
          triggerLabel="+ Procurar trechos"
          toggleLabel="Procurar trechos repetidos"
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">Procurar trechos repetidos</span>
              <span className="text-xs text-(--color-muted)">
                A varredura registra candidatos inativos: nada entra no texto da IA antes de você aprovar um escopo.
              </span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              A varredura registra os candidatos como <strong>sugestões inativas</strong>: nada entra no
              texto da IA antes de você aprovar um escopo.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Fração mínima do acervo">
                <Input
                  type="number"
                  min={0.01}
                  max={1}
                  step={0.01}
                  value={minRatio}
                  onChange={(event) => setMinRatio(Number(event.target.value))}
                  className="w-32"
                />
              </Field>
              <Field label="Documentos mínimos">
                <Input
                  type="number"
                  min={2}
                  value={minDocuments}
                  onChange={(event) => setMinDocuments(Number(event.target.value))}
                  className="w-32"
                />
              </Field>
              <Button variant="primary" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
                {suggest.isPending ? "Varrendo…" : "Procurar"}
              </Button>
            </div>
            {suggest.data ? (
              <p className="text-xs text-(--color-muted)">
                {routeMessage(suggest.data)} {formatCount(suggest.data.documents_scanned)} documentos lidos ·{" "}
                {formatCount(suggest.data.persisted)} candidatos registrados.
              </p>
            ) : null}
            {suggest.error ? <ErrorState error={suggest.error} /> : null}
          </div>
        </Disclosure>

        {/* The two writes sit together at the top; the catalogue of excerpts comes after them. */}
        <NewTemplateCard onCreated={invalidate} />

        <div className="flex flex-wrap items-center gap-2">
          {([undefined, "SUGGESTED", "APPROVED", "REJECTED"] as (TemplateStatus | undefined)[]).map((status) => (
            <Button
              key={status ?? "ALL"}
              size="sm"
              variant={search.status === status ? "primary" : "secondary"}
              onClick={() => navigate({ to: "/qualidade/trechos", search: { status } })}
            >
              {status ? labelOf(TEMPLATE_STATUS_LABEL, status) : "Todos"}
            </Button>
          ))}
        </div>

        {templates.error ? <ErrorState error={templates.error} /> : null}
        {templates.isPending ? <Spinner /> : null}
        {templates.data && rows.length === 0 ? (
          <EmptyState
            title="Nenhum trecho neste filtro"
            hint="Rode a procura acima, ou escreva um trecho à mão. Os 5 candidatos do acervo real vieram dessa varredura: um bloco de escopo compartilhado por 2.467 documentos e o prefixo de título 'Registros Fotográficos -'."
          />
        ) : null}

        <ul className="grid gap-2">
          {rows.map((template) => (
            <TemplateCard key={template.template_id} template={template} onChanged={invalidate} />
          ))}
        </ul>
      </PageBody>
    </>
  );
}

function scopeOf(template: TextTemplate): TemplateScope[] {
  return (template.scope ?? ["EMBEDDING", "NER"]) as TemplateScope[];
}

function TemplateCard({ template, onChanged }: { template: TextTemplate; onChanged: () => void }) {
  const [preview, setPreview] = useState<TemplateDryRunResponse | null>(null);
  const [scope, setScope] = useState<TemplateScope[]>(scopeOf(template));

  const status = (template.status ?? "SUGGESTED") as TemplateStatus;

  const save = useMutation({
    mutationFn: (body: Parameters<typeof updateTextTemplate>[1]) =>
      updateTextTemplate(template.template_id, body),
    onSuccess: onChanged,
  });

  const dryRun = useMutation({
    mutationFn: () =>
      previewTextTemplate({
        text: template.text,
        action: (template.action ?? "IGNORE") as TemplateAction,
        replacement: template.replacement ?? "",
        scope,
        variants: template.variants ?? [],
        sample_limit: 5,
      }),
    onSuccess: setPreview,
  });

  const remove = useMutation({
    mutationFn: () => deleteTextTemplate(template.template_id),
    onSuccess: onChanged,
  });

  const dirty = scope.join(",") !== scopeOf(template).join(",");

  return (
    <Card>
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Badge tone={TEMPLATE_STATUS_TONE[status] ?? "neutral"}>{labelOf(TEMPLATE_STATUS_LABEL, status)}</Badge>
            <Badge tone="neutral" title="Documentos em que o trecho aparece">
              {formatCount(template.occurrence_count ?? 0)} documentos
            </Badge>
            <Badge tone={template.source === "SUGGESTED" ? "warn" : "accent"}>
              {template.source === "SUGGESTED" ? "sugerido pela máquina" : "escrito por humano"}
            </Badge>
            {!template.is_active ? <Badge tone="neutral">inativo</Badge> : null}
          </div>
          <code className="text-[10px] text-(--color-muted)">#{template.template_id}</code>
        </div>

        <p className="max-h-24 overflow-y-auto rounded bg-black/[0.03] px-2 py-1 font-mono text-xs break-words whitespace-pre-wrap">
          {template.text}
        </p>

        {(template.variants ?? []).length > 0 ? (
          <p className="text-xs text-(--color-muted)">
            grafias: {(template.variants ?? []).join(" · ")}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-(--color-muted)">sai de:</span>
          {SCOPES.map((value) => (
            <label key={value} className="flex items-center gap-1" title={TEMPLATE_SCOPE_HINT[value]}>
              <input
                type="checkbox"
                checked={scope.includes(value)}
                onChange={(event) =>
                  setScope((current) =>
                    event.target.checked ? [...current, value] : current.filter((item) => item !== value),
                  )
                }
              />
              <span>{labelOf(TEMPLATE_SCOPE_LABEL, value)}</span>
            </label>
          ))}
          {dirty ? (
            <Button
              size="sm"
              variant="primary"
              disabled={save.isPending}
              onClick={() => save.mutate({ scope })}
            >
              {save.isPending ? ACTION.save.pending : "Salvar escopo"}
            </Button>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" disabled={dryRun.isPending} onClick={() => dryRun.mutate()}>
            {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
          </Button>

          {status !== "APPROVED" ? (
            <Button
              size="sm"
              variant="primary"
              disabled={save.isPending}
              onClick={() => save.mutate({ status: "APPROVED", is_active: true, scope })}
            >
              Aprovar
            </Button>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              disabled={save.isPending}
              onClick={() => save.mutate({ is_active: false })}
            >
              {ACTION.retire.label}
            </Button>
          )}

          {status !== "REJECTED" ? (
            <Button size="sm" variant="ghost" disabled={save.isPending} onClick={() => save.mutate({ status: "REJECTED" })}>
              Rejeitar
            </Button>
          ) : null}

          <Button
            size="sm"
            variant="danger"
            disabled={remove.isPending}
            title="Remove do catálogo e devolve os documentos afetados à fila da IA"
            onClick={() => remove.mutate()}
          >
            {ACTION.remove.label}
          </Button>
        </div>

        {save.data ? (
          <p className="text-xs text-(--color-muted)">
            {routeMessage(save.data)} {formatCount(save.data.documents_requeued)} documentos voltaram à fila.
          </p>
        ) : null}
        {preview ? (
          <div className="rounded-md bg-black/[0.03] px-3 py-2 text-xs">
            <p>
              <strong>{formatCount(preview.documents_affected)}</strong> de{" "}
              {formatCount(preview.documents_scanned)} documentos mudariam.
            </p>
            {(preview.samples ?? []).length > 0 ? (
              <ul className="mt-1 grid gap-1">
                {(preview.samples ?? []).map((sample) => (
                  <li key={`${sample.description_id}-${sample.column}`} className="text-(--color-muted)">
                    <code>{sample.description_id}</code> · {sample.column}:{" "}
                    <span className="line-through">{sample.original_text.slice(0, 80)}</span> →{" "}
                    <span>{sample.modified_text.slice(0, 80)}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {save.error ? <ErrorState error={save.error} /> : null}
        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
        {remove.error ? <ErrorState error={remove.error} /> : null}
      </CardBody>
    </Card>
  );
}

/**
 * Writing an excerpt by hand.
 *
 * It starts **approved and applied**, so the preview is the step and not a convenience: the button
 * that writes stays disabled until the archivist has seen how many documents change.
 */
function NewTemplateCard({ onCreated }: { onCreated: () => void }) {
  const [text, setText] = useState("");
  const [action, setAction] = useState<TemplateAction>("IGNORE");
  const [replacement, setReplacement] = useState("");
  const [scope, setScope] = useState<TemplateScope[]>(["EMBEDDING", "NER"]);
  const [preview, setPreview] = useState<TemplateDryRunResponse | null>(null);

  const dryRun = useMutation({
    mutationFn: () =>
      previewTextTemplate({ text, action, replacement, scope, variants: [], sample_limit: 5 }),
    onSuccess: setPreview,
  });

  const create = useMutation({
    mutationFn: () => createTextTemplate({ text, action, replacement, scope, variants: [] }),
    onSuccess: () => {
      setText("");
      setReplacement("");
      setPreview(null);
      onCreated();
    },
  });

  return (
    <Disclosure
      triggerLabel="+ Escrever trecho"
      toggleLabel="Escrever um trecho"
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">Escrever um trecho</span>
          <span className="text-xs text-(--color-muted)">
            Criar o trecho já o aplica e devolve os documentos afetados à fila da IA; só libera depois do impacto.
          </span>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="text-xs text-(--color-muted)">
          Criar o trecho já o aplica e devolve os documentos afetados à fila da IA. Por isso o
          botão de criar só libera depois de conferir o impacto.
        </p>
        <textarea
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setPreview(null);
          }}
          rows={3}
          placeholder="trecho exato, como aparece nos documentos"
          className="w-full rounded-md bg-white px-3 py-2 font-mono text-xs ring-1 ring-(--color-line) focus:ring-2 focus:ring-(--color-accent) focus:outline-none"
        />
        <div className="flex flex-wrap items-end gap-3">
          <Field label="O que fazer com ele">
            <Select
              value={action}
              onChange={(event) => setAction(event.target.value as TemplateAction)}
              className="w-48"
            >
              {(["IGNORE", "REPLACE"] as TemplateAction[]).map((value) => (
                <option key={value} value={value}>
                  {TEMPLATE_ACTION_LABEL[value]}
                </option>
              ))}
            </Select>
          </Field>
          {action === "REPLACE" ? (
            <label className="flex flex-1 flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">Substituir por</span>
              <Input
                value={replacement}
                onChange={(event) => setReplacement(event.target.value)}
                placeholder="texto que fica no lugar"
              />
            </label>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-(--color-muted)">sai de:</span>
          {SCOPES.map((value) => (
            <label key={value} className="flex items-center gap-1" title={TEMPLATE_SCOPE_HINT[value]}>
              <input
                type="checkbox"
                checked={scope.includes(value)}
                onChange={(event) => {
                  setPreview(null);
                  setScope((current) =>
                    event.target.checked ? [...current, value] : current.filter((item) => item !== value),
                  );
                }}
              />
              <span>{labelOf(TEMPLATE_SCOPE_LABEL, value)}</span>
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={text.trim().length === 0 || dryRun.isPending}
            onClick={() => dryRun.mutate()}
          >
            {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={text.trim().length === 0 || preview === null || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? ACTION.create.pending : "Criar e aplicar"}
          </Button>
        </div>
        {preview ? (
          <p className="text-xs text-(--color-muted)">
            {formatCount(preview.documents_affected)} de {formatCount(preview.documents_scanned)}{" "}
            documentos mudariam.
          </p>
        ) : null}
        {create.data ? (
          <p className="text-xs text-(--color-muted)">
            {routeMessage(create.data)} {formatCount(create.data.documents_requeued)} documentos na fila.
          </p>
        ) : null}
        {create.error ? <ErrorState error={create.error} /> : null}
        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
      </div>
    </Disclosure>
  );
}

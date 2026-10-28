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
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";

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
  const messages = useCopy();
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
              ? messages.pages.textTemplates.statusEmpty
              : fill(messages.pages.textTemplates.statusCount, { count: formatCount(rows.length) })
            : undefined
        }
      />

      <PageBody>
        <Notice tone="accent">{messages.pages.textTemplates.notice}</Notice>

        <Disclosure
          triggerLabel={messages.pages.textTemplates.searchTrigger}
          toggleLabel={messages.pages.textTemplates.searchToggle}
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">{messages.pages.textTemplates.searchToggle}</span>
              <span className="text-xs text-(--color-muted)">{messages.pages.textTemplates.searchHint}</span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">{messages.pages.textTemplates.scanHint}</p>
            <div className="flex flex-wrap items-end gap-3">
              <Field label={messages.pages.textTemplates.minRatio}>
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
              <Field label={messages.pages.textTemplates.minDocuments}>
                <Input
                  type="number"
                  min={2}
                  value={minDocuments}
                  onChange={(event) => setMinDocuments(Number(event.target.value))}
                  className="w-32"
                />
              </Field>
              <Button variant="primary" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
                {suggest.isPending ? messages.pages.textTemplates.scanning : messages.pages.textTemplates.search}
              </Button>
            </div>
            {suggest.data ? (
              <p className="text-xs text-(--color-muted)">
                {routeMessage(suggest.data)}{" "}
                {fill(messages.pages.textTemplates.scannedLine, {
                  scanned: formatCount(suggest.data.documents_scanned),
                  persisted: formatCount(suggest.data.persisted),
                })}
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
              {status ? labelOf(TEMPLATE_STATUS_LABEL, status) : messages.pages.textTemplates.allStatuses}
            </Button>
          ))}
        </div>

        {templates.error ? <ErrorState error={templates.error} /> : null}
        {templates.isPending ? <Spinner /> : null}
        {templates.data && rows.length === 0 ? (
          <EmptyState
            title={messages.pages.textTemplates.emptyTitle}
            hint={messages.pages.textTemplates.emptyHint}
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
  const messages = useCopy();
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
            <Badge tone="neutral" title={messages.pages.textTemplates.documentsBadgeTitle}>
              {formatCount(template.occurrence_count ?? 0)} documentos
            </Badge>
            <Badge tone={template.source === "SUGGESTED" ? "warn" : "accent"}>
              {template.source === "SUGGESTED"
                ? messages.pages.textTemplates.machineSuggested
                : messages.pages.textTemplates.humanWritten}
            </Badge>
            {!template.is_active ? <Badge tone="neutral">{messages.pages.textTemplates.inactive}</Badge> : null}
          </div>
          <code className="text-[10px] text-(--color-muted)">#{template.template_id}</code>
        </div>

        <p className="max-h-24 overflow-y-auto rounded bg-black/[0.03] px-2 py-1 font-mono text-xs break-words whitespace-pre-wrap">
          {template.text}
        </p>

        {(template.variants ?? []).length > 0 ? (
          <p className="text-xs text-(--color-muted)">
            {fill(messages.pages.textTemplates.variants, { list: (template.variants ?? []).join(" · ") })}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-(--color-muted)">{messages.pages.textTemplates.removeFrom}</span>
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
              {save.isPending ? ACTION.save.pending : messages.pages.textTemplates.saveScope}
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
              {messages.pages.textTemplates.approve}
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
              {messages.pages.textTemplates.reject}
            </Button>
          ) : null}

          <Button
            size="sm"
            variant="danger"
            disabled={remove.isPending}
            title={messages.pages.textTemplates.removeTitle}
            onClick={() => remove.mutate()}
          >
            {ACTION.remove.label}
          </Button>
        </div>

        {save.data ? (
          <p className="text-xs text-(--color-muted)">
            {routeMessage(save.data)}{" "}
            {fill(messages.pages.textTemplates.requeued, {
              count: formatCount(save.data.documents_requeued),
            })}
          </p>
        ) : null}
        {preview ? (
          <div className="rounded-md bg-black/[0.03] px-3 py-2 text-xs">
            <p>
              {fill(messages.pages.textTemplates.previewSummary, {
                affected: formatCount(preview.documents_affected),
                scanned: formatCount(preview.documents_scanned),
              })}
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
  const messages = useCopy();
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
      triggerLabel={messages.pages.textTemplates.newTrigger}
      toggleLabel={messages.pages.textTemplates.newToggle}
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">{messages.pages.textTemplates.newToggle}</span>
          <span className="text-xs text-(--color-muted)">{messages.pages.textTemplates.newHint}</span>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="text-xs text-(--color-muted)">{messages.pages.textTemplates.newExplain}</p>
        <textarea
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setPreview(null);
          }}
          rows={3}
          placeholder={messages.pages.textTemplates.textPlaceholder}
          className="w-full rounded-md bg-white px-3 py-2 font-mono text-xs ring-1 ring-(--color-line) focus:ring-2 focus:ring-(--color-accent) focus:outline-none"
        />
        <div className="flex flex-wrap items-end gap-3">
          <Field label={messages.pages.textTemplates.actionField}>
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
              <span className="text-(--color-muted)">{messages.pages.textTemplates.replaceWith}</span>
              <Input
                value={replacement}
                onChange={(event) => setReplacement(event.target.value)}
                placeholder={messages.pages.textTemplates.replacementPlaceholder}
              />
            </label>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-(--color-muted)">Remover de:</span>
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
            {create.isPending ? ACTION.create.pending : messages.pages.textTemplates.createApply}
          </Button>
        </div>
        {preview ? (
          <p className="text-xs text-(--color-muted)">
            {fill(messages.pages.textTemplates.previewSummary, {
              affected: formatCount(preview.documents_affected),
              scanned: formatCount(preview.documents_scanned),
            })}
          </p>
        ) : null}
        {create.data ? (
          <p className="text-xs text-(--color-muted)">
            {routeMessage(create.data)}{" "}
            {fill(messages.pages.textTemplates.queued, {
              count: formatCount(create.data.documents_requeued),
            })}
          </p>
        ) : null}
        {create.error ? <ErrorState error={create.error} /> : null}
        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
      </div>
    </Disclosure>
  );
}

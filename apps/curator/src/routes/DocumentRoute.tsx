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
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { Trans } from "@/i18n/trans";
import { ACTION, DIGITAL_OBJECT } from "@/lib/copy";
import { ENTITY_ORIGIN_HINT, ENTITY_ORIGIN_LABEL, ENTITY_ORIGIN_TONE } from "@/lib/entities";
import { formatCount, formatDate, formatDateTime, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";
import { fieldsOfArea, ISAD_AREAS } from "@/lib/isad";
import { Hint } from "@/components/ui/Hint";

const routeApi = getRouteApi("/acervo/$descriptionId");

/**
 * The dossier.
 *
 * The tabs are in the URL because each one is a shareable statement ("look at the subjects of this
 * one"), and the back button has to walk between them.
 */
export function DocumentRoute() {
  const messages = useCopy();
  const { descriptionId } = routeApi.useParams();
  const { aba = "descricao" } = routeApi.useSearch();
  const navigate = routeApi.useNavigate();

  const document = useQuery(queries.document(descriptionId));
  const tabItems = [
    { id: "descricao", label: messages.pages.document.tabs.description },
    { id: "assuntos", label: messages.pages.document.tabs.subjects },
    { id: "arranjo", label: messages.pages.document.tabs.arrangement },
    { id: "historico", label: messages.pages.document.tabs.history },
  ];

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
              {document.data.is_published ? <Badge tone="ok">{messages.pages.document.published}</Badge> : null}
              {document.data.is_anomaly ? <Badge tone="warn">{messages.pages.preview.anomaly}</Badge> : null}
              <span>{formatDate(document.data.document_date)}</span>
              {document.data.level ? <span>· {document.data.level}</span> : null}
            </span>
          ) : undefined
        }
        actions={
          <Link to="/acervo/lista" className="text-sm text-(--color-muted) hover:underline">
            {messages.pages.document.backToList}
          </Link>
        }
      />

      <div className="px-6 pt-4">
        <Tabs
          items={tabItems}
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
// TAB: DESCRIPTION
// ==========================================

function DescriptionTab({ document }: { document: DocumentSummary }) {
  const messages = useCopy();
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
        <CardHeader className="text-sm font-semibold">{messages.pages.document.image}</CardHeader>
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
              <p className="text-xs font-semibold tracking-wide text-(--color-muted) uppercase">
                {messages.pages.document.suggestedTitle}
              </p>
              <p className="text-sm">{document.suggested_final_title}</p>
              <p className="text-xs text-(--color-muted)">{messages.pages.document.suggestedTitleHint}</p>
            </div>
            <Button
              onClick={() => setDraft((previous) => ({ ...previous, final_title: document.suggested_final_title ?? "" }))}
            >
              {messages.pages.document.useSuggestedTitle}
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
                <Field
                  label={messages.pages.document.fields.originalTitle}
                  hint={messages.pages.document.fields.originalTitleHint}
                >
                  <Input value={valueOf("original_title")} onChange={(event) => setField("original_title", event.target.value)} />
                </Field>
                <Field
                  label={messages.pages.document.fields.finalTitle}
                  hint={messages.pages.document.fields.finalTitleHint}
                >
                  <Input value={valueOf("final_title")} onChange={(event) => setField("final_title", event.target.value)} />
                </Field>
                <Field label={messages.pages.newDescription.levelLabel}>
                  <Select
                    value={levels ?? ""}
                    onChange={(event) => setLevels(event.target.value ? Number(event.target.value) : undefined)}
                  >
                    <option value="">{messages.pages.newDescription.unclassified}</option>
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
                <Field label={messages.pages.document.fields.typology}>
                  <Select
                    value={typology ?? ""}
                    onChange={(event) => setTypology(event.target.value ? Number(event.target.value) : undefined)}
                  >
                    <option value="">{messages.pages.document.fields.typologyUnclassified}</option>
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
                    ? fill(messages.pages.document.fields.dateHint, { expression: document.date_expression })
                    : undefined
                }
              />
            ))}

            {area.id === "identity" ? <ParentReference document={document} /> : null}

            {area.id === "context" && document.original_url ? (
              <div className="grid gap-1 text-xs sm:col-span-2">
                <span className="text-(--color-muted)">{messages.pages.document.fields.sourceLabel}</span>
                <a
                  className="truncate text-sm underline"
                  href={document.original_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {document.original_url}
                </a>
                <span className="text-(--color-muted)">{messages.pages.document.fields.sourceHint}</span>
              </div>
            ) : null}
          </CardBody>
        </Card>
      ))}

      <Card>
        <CardHeader className="text-sm font-semibold">{messages.pages.document.diffusion.title}</CardHeader>
        <CardBody>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={published} onChange={(event) => setPublished(event.target.checked)} />
            <span className="text-sm">
              {messages.pages.document.diffusion.publish}
              <Hint label={messages.pages.document.diffusion.publish} className="text-xs">
                <Trans
                  text={messages.pages.document.diffusion.publishHint}
                  values={{ notBlocked: <strong>{messages.pages.document.diffusion.notBlocked}</strong> }}
                />
              </Hint>
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
          <Field label={messages.pages.document.editReason}>
            <Input value={note} onChange={(event) => setNote(event.target.value)} />
          </Field>
          <div className="sm:col-span-2">
            <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? ACTION.save.pending : messages.pages.document.saveReviewed}
            </Button>
            <span className="ml-3 text-xs text-(--color-muted)">{messages.pages.document.saveHint}</span>
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
  const messages = useCopy();
  // The parent is the last rung of the branch the read view already carries, so the line can name
  // it even when the origin declared no code. A raw ``description_id`` is the last resort: it is
  // what the archive knows when the arrangement has a parent the reader cannot resolve.
  const branch = (document.ancestors ?? []).at(-1);
  const parentLabel = branch?.title ?? document.parent_reference_code ?? messages.pages.document.parent.unknown;

  return (
    <div className="grid gap-1 text-xs sm:col-span-2">
      <span className="text-(--color-muted)">{messages.pages.document.parent.label}</span>
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
          {fill(messages.pages.document.parent.declared, { code: document.parent_reference_code })}
        </span>
      ) : (
        <span className="text-sm text-(--color-muted)">{messages.pages.document.parent.notDeclared}</span>
      )}
    </div>
  );
}

// ==========================================
// TAB: SUBJECTS
// ==========================================

function SubjectsTab({ document }: { document: DocumentSummary }) {
  const messages = useCopy();
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
        <Trans
          text={messages.pages.document.subjects.notice}
          values={{ humanReviewed: <strong>{messages.pages.document.subjects.humanReviewed}</strong> }}
        />
      </Notice>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <span className="text-sm font-semibold">{messages.pages.document.subjects.tagsTitle}</span>
          <span className="text-xs text-(--color-muted)">
            {fill(messages.pages.document.subjects.categoriesAssigned, {
              count: document.macro_categories?.length ?? 0,
            })}
          </span>
        </CardHeader>
        <CardBody className="grid gap-2">
          {tags.length === 0 ? (
            <EmptyState
              title={messages.pages.document.subjects.emptyTagsTitle}
              hint={messages.pages.document.subjects.emptyTagsHint}
            />
          ) : null}

          <ul className="divide-y divide-(--color-line)">
            {tags.map((tag) => (
              <li key={tag.tag_id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm">{tag.name}</span>
                  {tag.macro_category_name ? (
                    <Badge
                      tone="accent"
                      title={fill(messages.pages.document.subjects.confidence, {
                        score: tag.ai_confidence_score ?? "—",
                      })}
                    >
                      {tag.macro_category_name}
                    </Badge>
                  ) : (
                    <Badge tone="neutral" title={messages.pages.document.subjects.notClassified}>
                      {messages.pages.newDescription.noCategory}
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
                    aria-label={fill(messages.pages.document.subjects.tagCategoryAria, { name: tag.name })}
                    value={tag.macro_category_id ?? ""}
                    disabled={reclassify.isPending}
                    title={messages.pages.document.subjects.reclassifyTitle}
                    onChange={(event) =>
                      reclassify.mutate({
                        tagId: tag.tag_id,
                        categoryId: event.target.value ? Number(event.target.value) : null,
                      })
                    }
                  >
                    <option value="">{messages.pages.document.subjects.noCategoryOption}</option>
                    {drawers.map((category) => (
                      <option key={category.category_id} value={category.category_id}>
                        {category.name}
                        {category.is_active ? "" : ` (${messages.pages.categories.retiredBadge})`}
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
                {messages.pages.document.subjects.addTagLabel}
              </span>
              <Typeahead
                placeholder={messages.pages.document.subjects.tagPlaceholder}
                disabled={addTag.isPending}
                emptyLabel={messages.pages.document.subjects.tagEmpty}
                onSearch={async (term) =>
                  (await searchTags(term)).map((result) => ({
                    value: String(result.tag_id),
                    label: result.name,
                    hint: result.macro_category_name
                      ? fill(messages.pages.document.subjects.tagHint, {
                          count: formatCount(result.document_count),
                          category: result.macro_category_name,
                        })
                      : fill(messages.pages.document.subjects.tagHintNoCategory, {
                          count: formatCount(result.document_count),
                        }),
                  }))
                }
                onPick={(option) => addTag.mutate(Number(option.value))}
              />
            </label>
          </div>
          <p className="text-xs text-(--color-muted)">
            <Trans
              text={messages.pages.document.subjects.categoryNotice}
              values={{
                all: <strong>{messages.pages.document.subjects.all}</strong>,
                noCategory: <em>{messages.pages.document.subjects.noCategoryEmphasis}</em>,
              }}
            />
          </p>
          {addTag.error ? <ErrorState error={addTag.error} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">{messages.pages.document.subjects.entitiesTitle}</CardHeader>
        <CardBody className="grid gap-2">
          {entities.length === 0 ? (
            <EmptyState
              title={messages.pages.document.subjects.emptyEntitiesTitle}
              hint={messages.pages.document.subjects.emptyEntitiesHint}
            />
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
                      title={messages.pages.document.subjects.confirmTitle}
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
              {messages.pages.document.subjects.addEntityLabel}
            </span>
            <Typeahead
              placeholder={messages.pages.document.subjects.entityPlaceholder}
              disabled={addEntity.isPending}
              emptyLabel={messages.pages.document.subjects.entityEmpty}
              onSearch={async (term) =>
                (await searchEntities(term)).map((result) => ({
                  value: String(result.entity_id),
                  label: result.name,
                  hint: fill(messages.pages.document.subjects.entityHint, {
                    type: result.entity_type,
                    count: formatCount(result.total_usage),
                  }),
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
// TAB: ARRANGEMENT
// ==========================================

function ArrangementTab({ document }: { document: DocumentSummary }) {
  const messages = useCopy();
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
        <CardHeader className="text-sm font-semibold">{messages.pages.document.arrangement.pathTitle}</CardHeader>
        <CardBody>
          {ancestors.length === 0 ? (
            <EmptyState
              title={messages.pages.document.arrangement.rootTitle}
              hint={messages.pages.document.arrangement.rootHint}
              action={
                <Link to="/arranjo/plano">
                  <Button size="sm">{messages.pages.diagnostics.openPlan}</Button>
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
        <CardHeader className="text-sm font-semibold">{messages.pages.document.arrangement.unitTitle}</CardHeader>
        <CardBody className="grid gap-3">
          <p className="text-xs text-(--color-muted)">{messages.pages.document.arrangement.moveNotice}</p>

          <div className="grid gap-2 sm:grid-cols-2">
            <Field
              label={fill(messages.pages.document.arrangement.currentParent, {
                parent: currentParentTitle ?? messages.pages.document.arrangement.root,
              })}
            >
              <Typeahead
                placeholder={messages.pages.document.arrangement.parentPlaceholder}
                disabled={move.isPending}
                emptyLabel={messages.pages.document.arrangement.parentEmpty}
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

            <Field label={messages.pages.newDescription.levelLabel}>
              <Select
                value={levelId ?? ""}
                onChange={(event) => setLevelId(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">{messages.pages.document.arrangement.keepLevel}</option>
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
            <Field label={messages.pages.document.arrangement.decisionNote}>
              <Input value={note} onChange={(event) => setNote(event.target.value)} />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" disabled={move.isPending} onClick={() => move.mutate(parentId)}>
              {move.isPending ? messages.pages.document.arrangement.moving : messages.pages.document.arrangement.moveTo}
            </Button>
            <Button
              disabled={move.isPending || parentId === null}
              title={messages.pages.document.arrangement.promoteTitle}
              onClick={() => move.mutate(null)}
            >
              {messages.pages.document.arrangement.promote}
            </Button>
            <Button
              variant="ghost"
              disabled={move.isPending}
              onClick={() => navigate({ to: "/arranjo/diagnostico", search: { issue: "LEVEL_DEPTH_MISMATCH" } })}
            >
              {messages.pages.document.arrangement.levelIssues}
            </Button>
          </div>

          {move.error ? <ErrorState error={move.error} /> : null}
          {move.data ? (
            <Notice tone="ok">
              <Trans
                text={messages.pages.document.arrangement.moved}
                values={{
                  parent: move.data.parent_id ?? messages.pages.document.arrangement.rootArticle,
                  path: <code>{move.data.path}</code>,
                }}
              />
            </Notice>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">{messages.pages.document.arrangement.childrenTitle}</CardHeader>
        <CardBody className="text-sm">
          {document.children_count === 0 ? (
            <p className="text-(--color-muted)">{messages.pages.document.arrangement.childrenNone}</p>
          ) : (
            <p>
              <Trans
                text={messages.pages.document.arrangement.childrenCount}
                values={{ count: <strong>{formatCount(document.children_count)}</strong> }}
              />
            </p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">{messages.pages.document.arrangement.publicationTitle}</CardHeader>
        <CardBody className="text-sm">
          {document.is_published ? (
            <Badge tone="ok">{messages.pages.document.arrangement.publishedDiffusion}</Badge>
          ) : (
            <Badge tone="neutral">{messages.pages.document.arrangement.notPublished}</Badge>
          )}
          <p className="mt-2 text-xs text-(--color-muted)">
            {messages.pages.document.arrangement.publicationHint}
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

// ==========================================
// TAB: HISTORY
// ==========================================

function HistoryTab({ document }: { document: DocumentSummary }) {
  const messages = useCopy();
  const descriptionId = document.description_id;
  const { data, isPending, error } = useQuery(queries.revisions(descriptionId));

  if (error) return <ErrorState error={error} />;
  if (isPending) return <Spinner />;

  return (
    <div className="grid gap-4">
      {!data || data.length === 0 ? (
        <EmptyState
          title={messages.pages.document.history.emptyTitle}
          hint={messages.pages.document.history.emptyHint}
        />
      ) : (
        <ol className="space-y-3">
          {data.map((revision) => (
            <li key={revision.revision_id}>
              <Card>
                <CardHeader className="flex items-center justify-between text-sm">
                  <span className="font-medium">
                    {revision.changed_by ?? messages.pages.document.history.unknownAuthor}
                  </span>
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
  const messages = useCopy();
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
            <p className="text-sm font-semibold text-(--color-danger)">{messages.pages.document.delete.title}</p>
            <p className="text-xs text-(--color-muted)">{messages.pages.document.delete.hint}</p>
          </div>
          <Button size="sm" variant="danger" onClick={() => setOpen((current) => !current)}>
            {open ? ACTION.cancel.label : messages.pages.document.delete.open}
          </Button>
        </div>

        {open ? (
          <Notice tone="danger" as="div" className="grid gap-3">
            <p className="text-xs text-(--color-danger)">
              <Trans
                text={messages.pages.document.delete.notice}
                values={{ cannot: <strong>{messages.pages.document.delete.cannot}</strong> }}
              />
            </p>

            <Field
              label={
                <Trans
                  text={messages.pages.document.delete.confirmLabel}
                  values={{ code: <code>{expected}</code> }}
                />
              }
            >
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
              <Field label={messages.pages.document.delete.reason}>
                <Input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder={messages.pages.document.delete.reasonPlaceholder}
                />
              </Field>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="danger"
                disabled={!matches || remove.isPending}
                title={matches ? undefined : messages.pages.document.delete.mismatchTitle}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? ACTION.exclude.pending : messages.pages.document.delete.confirm}
              </Button>
              <span className="text-xs text-(--color-muted)">
                {matches ? messages.pages.document.delete.matches : messages.pages.document.delete.notMatches}
              </span>
            </div>

            {remove.error ? <ErrorState error={remove.error} /> : null}
            {done ? (
              <p className="text-xs text-(--color-ok)">
                {fill(messages.pages.document.delete.done, { title: done.title })}
              </p>
            ) : null}
          </Notice>
        ) : null}
      </CardBody>
    </Card>
  );
}

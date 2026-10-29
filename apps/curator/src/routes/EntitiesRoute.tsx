import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  deleteEntity,
  mergeEntities,
  previewEntityMerge,
  purgeOrphanEntities,
  reclassifyEntity,
  renameEntity,
  searchEntities,
  undoEntityMerge,
  type EntityPairSimilarity,
  type EntityRelevance,
  type EntityRenameRequest,
  type EntitySimilarity,
  type EntityType,
  type ReclassifyTarget,
} from "@/api/client";
import { ENTITY_DOCUMENTS_PAGE_SIZE, queries, RELEVANCE_PAGE_SIZE } from "@/api/queries";
import { DescriptionExpansion } from "@/components/description/DescriptionExpansion";
import { DescriptionPreview } from "@/components/description/DescriptionPreview";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { Typeahead, type TypeaheadOption } from "@/components/ui/Typeahead";
import { PageBody } from "@/components/layout/PageBody";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { Trans } from "@/i18n/trans";
import { ACTION } from "@/lib/copy";
import {
  ENTITY_MERGE_FLAG_HINT,
  ENTITY_MERGE_FLAG_LABEL,
  ENTITY_TYPE_HINT,
  ENTITY_TYPE_LABEL,
  ENTITY_TYPE_TONE,
} from "@/lib/entities";
import { descricoes, formatCount, formatDateTime } from "@/lib/format";
import { asEnum, asNumber, asString } from "@/lib/search";
import { labelOf } from "@/lib/hierarchy";
import { routeMessage } from "@/lib/messages";

const routeApi = getRouteApi("/entidades/lista");

/**
 * The URL is the state, as on every other list.
 *
 * ``aberta``, ``descricao`` and ``offset`` are the expansion's three questions: which name is open
 * (one at a time — the page is a list of names, not a dashboard), which page of **that** name's
 * descriptions is showing, and which description the panel is previewing. Keeping them here is what
 * makes the back button close the panel, and what lets a colleague be sent the exact view.
 */
export type EntitiesSearch = {
  aba?: "relevancia" | "similaridade";
  tipo?: EntityType;
  limiar?: number;
  aberta?: number;
  descricao?: string;
  offset?: number;
};

const TYPE_VALUES: ReclassifyTarget[] = ["ORG", "PER", "LOC"];

/**
 * One entity a merge panel may absorb.
 *
 * The ids travel together with the names because the two lists a merge can start from are different
 * screens: the similarity pair may name an entity that is not on the relevance page at all, and a
 * panel that looked the name up there would label the canonical with a bare id.
 */
type EntityCandidate = { entity_id: number; name: string };

export function validateEntitiesSearch(search: Record<string, unknown>): EntitiesSearch {
  const aba = search.aba === "similaridade" ? "similaridade" : "relevancia";
  const tipo = asEnum(search.tipo, TYPE_VALUES);
  const limiar = asNumber(search.limiar);
  return {
    aba,
    tipo,
    limiar: limiar !== undefined && limiar > 0 && limiar <= 1 ? limiar : undefined,
    aberta: asNumber(search.aberta),
    descricao: asString(search.descricao),
    offset: asNumber(search.offset),
  };
}

/** How many similarity rows are drawn before the archivist asks for the rest. */
const WINDOW = 100;

/**
 * The named-entity vocabulary.
 *
 * The screen exists to make one thing unmistakable: **reclassifying teaches the extractor**, and
 * **merging is reversible**. The write is logged per absorbed entity in the merge ledger before
 * anything changes, so the panel shows the impact and offers the undo, and the ledger at the bottom
 * keeps the trail.
 */
export function EntitiesRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const messages = useCopy();

  const [selected, setSelected] = useState<number[]>([]);

  const tab = search.aba ?? "relevancia";

  const relevance = useQuery(queries.entityRelevance(search.tipo, RELEVANCE_PAGE_SIZE));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "entities"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "conflicts"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };
  const purgeOrphans = useMutation({
    mutationFn: purgeOrphanEntities,
    onSuccess: invalidate,
  });

  const rows = relevance.data?.data ?? [];

  /**
   * ``offset: changes.offset`` and not a literal: opening another name has to return to **its** first
   * page — page 3 of the previous name means nothing — and a caller that wants the first page sends no
   * page at all. The literal-after-the-spread shape is what
   * ``testing/unit/curator/test_curator_search_state.py`` exists to catch, because it silently
   * discarded the page a caller had just set.
   */
  const patch = (changes: Partial<EntitiesSearch>) =>
    navigate({ to: "/entidades/lista", search: { ...search, ...changes, offset: changes.offset } });

  /**
   * The preview is not a filter, so it does not go through ``patch``: opening a row on page 3 and
   * closing the panel has to leave the archivist on page 3.
   */
  const showPreview = (descriptionId: string | undefined) =>
    navigate({ to: "/entidades/lista", search: { ...search, descricao: descriptionId } });

  const toggle = (entityId: number) =>
    setSelected((current) =>
      current.includes(entityId) ? current.filter((id) => id !== entityId) : [...current, entityId],
    );

  /**
   * The names travel with the ids instead of being looked up in the relevance list.
   *
   * They are two different lists: a name unified from the similarity tab may not be in the page of
   * "the 50 heaviest", and the panel would then label the canonical as ``#70317`` — an identifier the
   * archivist cannot check against anything.
   */
  const membersOf = (ids: number[]): EntityCandidate[] =>
    ids.map((entityId) => ({
      entity_id: entityId,
      name: rows.find((row) => row.entity_id === entityId)?.name ?? `#${entityId}`,
    }));

  const clear = () => setSelected([]);

  return (
    <>
      <PageHeader
        screen="entities"
        pending={relevance.isPending}
        status={
          relevance.data
            ? fill(messages.pages.entitiesScreen.status, {
                names: formatCount(rows.length),
                links: formatCount(rows.reduce((sum, row) => sum + row.total_usage, 0)),
              })
            : undefined
        }
        actions={
          <Button
            size="sm"
            variant="danger"
            disabled={purgeOrphans.isPending}
            title={messages.pages.entitiesScreen.purgeTitle}
            onClick={() => purgeOrphans.mutate()}
          >
            {purgeOrphans.isPending ? ACTION.exclude.pending : messages.pages.entitiesScreen.purgeOrphans}
          </Button>
        }
      />

      <PageBody>
        <Notice tone="accent">
          <Trans
            text={messages.pages.entitiesScreen.notice}
            values={{
              reclassify: <strong>{messages.pages.entitiesScreen.noticeReclassify}</strong>,
              merge: <strong>{messages.pages.entitiesScreen.noticeMerge}</strong>,
            }}
          />
        </Notice>

        {purgeOrphans.data ? (
          <p className="text-xs text-(--color-muted)">
            {routeMessage(purgeOrphans.data)}{" "}
            {fill(messages.pages.entitiesScreen.purgedCount, {
              count: formatCount(purgeOrphans.data.entities_deleted),
            })}
          </p>
        ) : null}
        {purgeOrphans.error ? <ErrorState error={purgeOrphans.error} /> : null}

        {/*
          Above the tabs and collapsed by default: browsing is the screen's first job, and the card is
          the third door into the merge panel — the one the two lists cannot reach.
        */}
        <MergeCard onMerged={invalidate} />

        <Tabs
          items={[
            { id: "relevancia", label: messages.pages.entitiesScreen.tabRelevance },
            { id: "similaridade", label: messages.pages.entitiesScreen.tabSimilarity },
          ]}
          active={tab}
          onChange={(aba) => navigate({ to: "/entidades/lista", search: { ...search, aba: aba as EntitiesSearch["aba"] } })}
        />

        {selected.length >= 2 ? (
          <MergePanel
            members={membersOf(selected)}
            onChanged={invalidate}
            onDone={() => {
              clear();
              invalidate();
            }}
            onCancel={clear}
          />
        ) : null}

        {tab === "relevancia" ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant={search.tipo === undefined ? "primary" : "secondary"}
                onClick={() => navigate({ to: "/entidades/lista", search: { ...search, tipo: undefined } })}
              >
                {messages.pages.entitiesScreen.allTypes}
              </Button>
              {TYPE_VALUES.map((type) => (
                <Button
                  key={type}
                  size="sm"
                  variant={search.tipo === type ? "primary" : "secondary"}
                  title={ENTITY_TYPE_HINT[type]}
                  onClick={() => navigate({ to: "/entidades/lista", search: { ...search, tipo: type } })}
                >
                  {ENTITY_TYPE_LABEL[type]}
                </Button>
              ))}
              {selected.length > 0 ? (
                <span className="text-xs text-(--color-muted)">
                  {fill(messages.pages.entitiesScreen.markedHint, { count: formatCount(selected.length) })}
                </span>
              ) : (
                <span className="text-xs text-(--color-muted)">{messages.pages.entitiesScreen.markHint}</span>
              )}
            </div>

            {relevance.error ? <ErrorState error={relevance.error} /> : null}
            {relevance.isPending ? <Spinner /> : null}
            {relevance.data && rows.length === 0 ? (
              <EmptyState
                title={messages.pages.entitiesScreen.emptyTitle}
                hint={messages.pages.entitiesScreen.emptyHint}
              />
            ) : null}

            <ul className="grid gap-2">
              {rows.map((row) => (
                <EntityRow
                  key={row.entity_id}
                  entity={row}
                  checked={selected.includes(row.entity_id)}
                  open={search.aberta === row.entity_id}
                  offset={search.aberta === row.entity_id ? (search.offset ?? 0) : 0}
                  onOpenChange={(next) => patch({ aberta: next ? row.entity_id : undefined })}
                  onPage={(offset) => patch({ offset })}
                  onPreview={showPreview}
                  onToggle={() => toggle(row.entity_id)}
                  onChanged={invalidate}
                />
              ))}
            </ul>
          </>
        ) : (
          <SimilarityTab onMerged={invalidate} />
        )}

        <EntityMergeLedger onChanged={invalidate} />
      </PageBody>

      {/*
        The panel is rendered by the screen and not by the row: the description being previewed is in
        the URL, so the panel survives a refetch of the list it was opened from — and a link that
        carries ``descricao`` opens on the record even when the current page does not list it.

        ``editTab`` is ``assuntos`` here and ``descricao`` on the category screen: an entity's links
        are added and removed on the dossier's Assuntos tab, which is the edit the archivist arrived
        here to make.
      */}
      {search.descricao ? (
        <DescriptionPreview
          descriptionId={search.descricao}
          editTab="assuntos"
          onClose={() => showPreview(undefined)}
        />
      ) : null}
    </>
  );
}

/**
 * One entity by weight, opened on the descriptions that carry it or on its name.
 *
 * The row is built like ``CategoryCard`` and for the reason ``Disclosure`` documents: the name and the
 * badges are **text inside the toggle**, while the controls — the checkbox, the type, the rename and
 * the delete — sit in ``actions``, outside it. A control nested in the toggle is a click that means
 * two things at once: checking a name for a merge would also open its descriptions.
 *
 * The body has two questions because a name is one object being both read and corrected. The
 * descriptions tab reads ``GET /api/v1/documents`` with ``entity_id``, so the badge above and the
 * ``total`` inside are one number counted twice
 * (``testing/integration/api/controller/test_entity_documents.py``); the edit tab is the rename, which
 * is its own write and never a merge.
 */
function EntityRow({
  entity,
  checked,
  open,
  offset,
  onOpenChange,
  onToggle,
  onPage,
  onPreview,
  onChanged,
}: {
  entity: EntityRelevance;
  checked: boolean;
  open: boolean;
  offset: number;
  onOpenChange: (open: boolean) => void;
  onToggle: () => void;
  onPage: (offset: number) => void;
  onPreview: (descriptionId: string) => void;
  onChanged: () => void;
}) {
  /**
   * Which of the two questions the open card is answering. Local state, like ``CategoryCard``'s: the
   * URL carries *which* card is open (``?aberta=``) and the page, not which tab of it is being read.
   */
  const [tab, setTab] = useState<string>("descricoes");
  const [draftName, setDraftName] = useState(entity.name);
  const [keepOldSpelling, setKeepOldSpelling] = useState(true);
  const messages = useCopy();

  const reclassify = useMutation({
    mutationFn: (newType: ReclassifyTarget) => reclassifyEntity(entity.entity_id, { new_type: newType }),
    onSuccess: onChanged,
  });

  const rename = useMutation({
    mutationFn: (body: EntityRenameRequest) => renameEntity(entity.entity_id, body),
    onSuccess: (data) => {
      setDraftName(data.name);
      onChanged();
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteEntity(entity.entity_id),
    onSuccess: onChanged,
  });

  const orphan = entity.total_usage === 0;
  const trimmed = draftName.trim();
  const dirty = trimmed.length > 0 && trimmed !== entity.name;

  /** The row's own door to the name. It opens the card on the edit tab and never merges anything. */
  const openRename = () => {
    setDraftName(entity.name);
    setTab("editar");
    if (!open) onOpenChange(true);
  };

  return (
    <li>
      <Disclosure
        open={open}
        onOpenChange={onOpenChange}
        toggleLabel={fill(messages.pages.entitiesScreen.openDescriptions, { name: entity.name })}
        header={
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium">{entity.name}</span>
            <Badge tone={ENTITY_TYPE_TONE[entity.entity_type] ?? "neutral"}>
              {labelOf(ENTITY_TYPE_LABEL, entity.entity_type)}
            </Badge>
            <Badge tone="neutral" title={messages.pages.entitiesScreen.usageBadgeTitle}>
              {descricoes(entity.total_usage)}
            </Badge>
          </div>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="checkbox"
              checked={checked}
              onChange={onToggle}
              aria-label={fill(messages.pages.entitiesScreen.selectEntity, { name: entity.name })}
            />
            <label className="flex items-center gap-1 text-xs text-(--color-muted)">
              {messages.pages.entitiesScreen.typeField}
              <Select
                className="h-7 w-32 text-xs"
                value={entity.entity_type}
                disabled={reclassify.isPending}
                onChange={(event) => reclassify.mutate(event.target.value as ReclassifyTarget)}
              >
                {TYPE_VALUES.map((type) => (
                  <option key={type} value={type}>
                    {ENTITY_TYPE_LABEL[type]}
                  </option>
                ))}
              </Select>
            </label>

            <Button
              size="sm"
              variant="ghost"
              title={messages.pages.entitiesScreen.renameTitle}
              aria-label={fill(messages.pages.entitiesScreen.renameAria, { name: entity.name })}
              onClick={openRename}
            >
              {ACTION.rename.label}
            </Button>

            {orphan ? (
              <Button
                size="sm"
                variant="danger"
                disabled={remove.isPending}
                title={messages.pages.entitiesScreen.deleteOrphanTitle}
                onClick={() => remove.mutate()}
              >
                {ACTION.exclude.label}
              </Button>
            ) : null}
          </div>
        }
      >
        <div className="grid gap-3">
          <Tabs
            items={[
              { id: "descricoes", label: messages.pages.entitiesScreen.tabDescriptions },
              { id: "editar", label: messages.common.edit },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "editar" ? (
            <div className="grid gap-2">
              <Field label={messages.pages.entitiesScreen.nameField}>
                <Input
                  value={draftName}
                  maxLength={255}
                  onChange={(event) => setDraftName(event.target.value)}
                />
              </Field>

              <label className="flex items-start gap-2 text-xs text-(--color-muted)">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={keepOldSpelling}
                  onChange={(event) => setKeepOldSpelling(event.target.checked)}
                />
                <span>{messages.pages.entitiesScreen.keepOldSpelling}</span>
              </label>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="primary"
                  disabled={!dirty || rename.isPending}
                  onClick={() => rename.mutate({ new_name: trimmed, keep_old_synonym: keepOldSpelling })}
                >
                  {rename.isPending ? ACTION.save.pending : ACTION.save.label}
                </Button>
                {dirty ? (
                  <span className="text-xs text-(--color-muted)">{messages.pages.entitiesScreen.unsaved}</span>
                ) : null}
              </div>

              {rename.data ? (
                <p className="text-xs text-(--color-muted)">
                  {routeMessage(rename.data)}{" "}
                  {rename.data.kept_old_spelling
                    ? messages.pages.entitiesScreen.renameKept
                    : messages.pages.entitiesScreen.renameNotKept}
                </p>
              ) : null}

              {rename.error ? <ErrorState error={rename.error} /> : null}
            </div>
          ) : (
            <DescriptionExpansion
              params={{ entity_id: entity.entity_id }}
              pageSize={ENTITY_DOCUMENTS_PAGE_SIZE}
              offset={offset}
              onPage={onPage}
              onPreview={onPreview}
              empty={{
                title: messages.pages.entitiesScreen.noDescriptionsTitle,
                hint: messages.pages.entitiesScreen.noDescriptionsHint,
              }}
            />
          )}

          {reclassify.error ? <ErrorState error={reclassify.error} /> : null}
          {remove.error ? <ErrorState error={remove.error} /> : null}
        </div>
      </Disclosure>
    </li>
  );
}

/**
 * A member of the card's own list: the pair the panel needs, plus the weight the type-ahead gave.
 *
 * The weight is the card's and not the panel's, because the panel shows `#id` and does not need it.
 * It is what lets the archivist see which of the two spellings is the heavy one **before** choosing
 * the canonical — the similarity rows cannot show it, and the type-ahead has it for free.
 */
type MergeCandidate = EntityCandidate & { hint: string };

/**
 * The third door into the merge panel: the pair the archivist writes by name.
 *
 * The other two doors are list-driven, and the archivist controls neither list. Relevância is ordered
 * by weight and capped at ``RELEVANCE_PAGE_SIZE``, so two names carried by very different numbers of
 * descriptions are never on the same page. Similaridade answers by trigram — the one measure that
 * fails on the pair they are most certain about: ``SMU`` and ``Secretaria Municipal do Urbanismo``
 * share no trigram run worth a threshold. So the pair they already know is one entity is the pair the
 * screen is least likely to show them.
 *
 * Three decisions this card owns, and none of them is the panel's:
 *
 * * **the list is the card's** and does not consume the checkboxes of the relevance tab. Two candidate
 *   sets that can silently diverge is how a panel ends up merging something the archivist never read;
 * * **the open state is local**, not a fourth key in the URL: a half-built list is a draft, not a view
 *   worth sending to a colleague;
 * * **the irreversibility warning is not repeated** — the panel already states that each absorbed
 *   entity enters the ledger before the write. One statement, one place.
 */
function MergeCard({ onMerged }: { onMerged: () => void }) {
  const [members, setMembers] = useState<MergeCandidate[]>([]);
  const messages = useCopy();

  const add = (option: TypeaheadOption) => {
    const entityId = Number(option.value);
    // Deduped by id: picking the same name twice is one member, and the panel's canonical radio is
    // still what decides which spelling survives.
    setMembers((current) =>
      current.some((member) => member.entity_id === entityId)
        ? current
        : [...current, { entity_id: entityId, name: option.label, hint: option.hint ?? "" }],
    );
  };

  const remove = (entityId: number) =>
    setMembers((current) => current.filter((member) => member.entity_id !== entityId));

  const clear = () => setMembers([]);

  return (
    <Disclosure
      triggerLabel={messages.pages.entitiesScreen.mergeByNameTrigger}
      toggleLabel={messages.pages.entitiesScreen.mergeByNameToggle}
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">{messages.pages.entitiesScreen.mergeByNameTitle}</span>
          <span className="text-xs text-(--color-muted)">{messages.pages.entitiesScreen.mergeByNameHint}</span>
        </div>
      }
    >
      <div className="grid gap-3">
        <Typeahead
          placeholder={messages.pages.entitiesScreen.mergeSearchPlaceholder}
          emptyLabel={messages.pages.entitiesScreen.mergeSearchEmpty}
          onSearch={async (term) =>
            (await searchEntities(term)).map((result) => ({
              value: String(result.entity_id),
              label: result.name,
              hint: `${labelOf(ENTITY_TYPE_LABEL, result.entity_type)} · ${descricoes(result.total_usage)}`,
            }))
          }
          onPick={add}
        />

        {members.length === 0 ? (
          <p className="text-xs text-(--color-muted)">{messages.pages.entitiesScreen.noMembersHint}</p>
        ) : (
          <ul className="divide-y divide-(--color-line) text-xs">
            {members.map((member) => (
              <li key={member.entity_id} className="flex items-center justify-between gap-2 py-1.5">
                <span className="min-w-0 truncate">
                  {member.name}
                  {member.hint ? <span className="text-(--color-muted)"> · {member.hint}</span> : null}
                </span>
                <Button size="sm" variant="ghost" onClick={() => remove(member.entity_id)}>
                  {ACTION.remove.label}
                </Button>
              </li>
            ))}
          </ul>
        )}

        {members.length < 2 ? (
          <p className="text-xs text-(--color-muted)">{messages.pages.entitiesScreen.needTwoHint}</p>
        ) : (
          <MergePanel
            members={members}
            title={messages.pages.entitiesScreen.mergeChosenTitle}
            hint={messages.pages.entitiesScreen.mergeChosenHint}
            onChanged={onMerged}
            onDone={() => {
              clear();
              onMerged();
            }}
            onCancel={clear}
          />
        )}
      </div>
    </Disclosure>
  );
}

/**
 * The confirmation step of a merge, and the only place the effect is stated.
 *
 * The impact comes from the preview route, computed by the same planner the write executes, so the
 * numbers here are the numbers the merge produces. The warning is a warning and not a refusal, and
 * the undo is real: the merge answers with the ledger ids, and the button reverses the click without
 * leaving the screen.
 */
function MergePanel({
  members,
  title,
  hint,
  onChanged,
  onDone,
  onCancel,
}: {
  members: EntityCandidate[];
  title?: string;
  hint?: string;
  onChanged: () => void;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [canonicalId, setCanonicalId] = useState(members[0]?.entity_id ?? 0);
  const [newName, setNewName] = useState("");
  const messages = useCopy();
  const nameOf = (id: number) => members.find((member) => member.entity_id === id)?.name ?? `#${id}`;

  const absorbed = members.filter((member) => member.entity_id !== canonicalId);

  // The preview is a read of the planner the write executes. It is keyed by the cluster and the
  // canonical because those are what the numbers depend on; the optional rename does not change them.
  const preview = useQuery({
    queryKey: ["taxonomy", "entities", "merge-preview", members.map((m) => m.entity_id).join("-"), canonicalId],
    queryFn: () =>
      previewEntityMerge({
        canonical_id: canonicalId,
        ids_to_merge: absorbed.map((member) => member.entity_id),
        new_name: null,
      }),
    enabled: absorbed.length > 0,
    staleTime: 30_000,
  });

  const merge = useMutation({
    mutationFn: () =>
      mergeEntities({
        canonical_id: canonicalId,
        ids_to_merge: absorbed.map((member) => member.entity_id),
        new_name: newName.trim() || null,
      }),
    onSuccess: onChanged,
  });

  const undo = useMutation({
    mutationFn: (mergeIds: number[]) => Promise.all(mergeIds.map(undoEntityMerge)),
    onSuccess: () => {
      onChanged();
      onDone();
    },
  });

  return (
    <Card className="ring-(--color-warn)/40">
      <CardBody className="grid gap-3">
        <p className="text-sm font-semibold">
          {title ?? fill(messages.pages.entitiesScreen.mergeCount, { count: formatCount(members.length) })}
        </p>
        {hint ? <p className="text-xs text-(--color-muted)">{hint}</p> : null}

        <div className="grid gap-2 text-xs">
          {members.map((member) => (
            <label key={member.entity_id} className="flex items-center gap-2">
              <input
                type="radio"
                name={`canonical-${members.map((item) => item.entity_id).join("-")}`}
                checked={canonicalId === member.entity_id}
                onChange={() => setCanonicalId(member.entity_id)}
              />
              <span className={canonicalId === member.entity_id ? "font-medium" : "text-(--color-muted)"}>
                {member.name} <code className="text-[10px]">#{member.entity_id}</code>
                {canonicalId === member.entity_id
                  ? messages.pages.entitiesScreen.canonicalSuffix
                  : messages.pages.entitiesScreen.absorbedSuffix}
              </span>
            </label>
          ))}
        </div>

        <Field label={messages.pages.entitiesScreen.renameCanonicalField}>
          <Input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder={nameOf(canonicalId)}
            className="max-w-md"
          />
        </Field>

        {/* The dry run, before the click: the same planner the merge executes computes these. */}
        {preview.isPending ? <Spinner label={messages.pages.entitiesScreen.previewPending} /> : null}
        {preview.error ? <ErrorState error={preview.error} /> : null}
        {preview.data ? (
          <p className="text-xs text-(--color-muted)">
            <Trans
              text={messages.pages.entitiesScreen.previewSummary}
              values={{
                descriptions: formatCount(preview.data.documents_updated),
                canonical: <strong>{nameOf(canonicalId)}</strong>,
                links: formatCount(preview.data.links_rewritten),
                entities: formatCount(preview.data.entities_deleted?.length ?? 0),
              }}
            />
          </p>
        ) : null}
        {preview.data && (preview.data.review_flags ?? []).length > 0 ? (
          <ul className="flex flex-wrap gap-2 text-xs">
            {(preview.data.review_flags ?? []).map((flag) => (
              <li key={flag}>
                <Badge tone="warn" title={ENTITY_MERGE_FLAG_HINT[flag]}>
                  {ENTITY_MERGE_FLAG_LABEL[flag] ?? flag}
                </Badge>
              </li>
            ))}
          </ul>
        ) : null}

        <Notice tone="warn">
          <Trans
            text={messages.pages.entitiesScreen.absorbNotice}
            values={{
              count: <strong>{formatCount(absorbed.length)}</strong>,
              name: <strong>{nameOf(canonicalId)}</strong>,
              before: <strong>{messages.pages.entitiesScreen.beforeMerge}</strong>,
            }}
          />
        </Notice>

        <div className="flex items-center gap-2">
          <Button variant="primary" disabled={merge.isPending || absorbed.length === 0} onClick={() => merge.mutate()}>
            {merge.isPending
              ? ACTION.merge.pending
              : absorbed.length === 1
                ? fill(messages.pages.entitiesScreen.mergeOne, {
                    absorbed: absorbed[0]?.name ?? "",
                    canonical: nameOf(canonicalId),
                  })
                : fill(messages.pages.entitiesScreen.mergeMany, {
                    count: formatCount(absorbed.length),
                    canonical: nameOf(canonicalId),
                  })}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            {ACTION.cancel.label}
          </Button>
        </div>

        {merge.data ? (
          <div className="grid gap-1 text-xs text-(--color-muted)">
            <p>
              <Trans
                text={messages.pages.entitiesScreen.mergeResult}
                values={{
                  links: formatCount(merge.data.documents_updated),
                  entities: formatCount(merge.data.entities_deleted),
                  ids: <code>{(merge.data.merge_ids ?? []).join(", ") || "—"}</code>,
                }}
              />
            </p>
            {(merge.data.merge_ids ?? []).length > 0 ? (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={undo.isPending}
                  title={messages.pages.entitiesScreen.undoTitle}
                  onClick={() => undo.mutate(merge.data.merge_ids ?? [])}
                >
                  {undo.isPending ? ACTION.undo.pending : messages.pages.entitiesScreen.undoMerge}
                </Button>
                <span>{messages.pages.entitiesScreen.undoAlsoInLedger}</span>
              </div>
            ) : null}
          </div>
        ) : null}
        {merge.error ? <ErrorState error={merge.error} /> : null}
        {undo.error ? <ErrorState error={undo.error} /> : null}
      </CardBody>
    </Card>
  );
}

/** How many ledger rows the entity screen reads at a time; "ver mais" grows the window. */
const ENTITY_MERGE_LOG_PAGE_SIZE = 50;

/**
 * The merge ledger: what was absorbed, by whom, and the undo of each row.
 *
 * Server-side search over both sides of each entry, exactly like the tag ledger: the trail only
 * grows, and a filter over the loaded page would answer "não está aqui" for a merge that happened.
 */
function EntityMergeLedger({ onChanged }: { onChanged: () => void }) {
  const [term, setTerm] = useState("");
  const [limit, setLimit] = useState(ENTITY_MERGE_LOG_PAGE_SIZE);
  const messages = useCopy();

  const log = useQuery(queries.entityMergeLog(limit, term.trim() || undefined));

  const undo = useMutation({
    mutationFn: (mergeId: number) => undoEntityMerge(mergeId),
    onSuccess: onChanged,
  });

  return (
    <Card>
      <CardHeader className="text-sm font-semibold">{messages.pages.entitiesScreen.ledgerTitle}</CardHeader>
      <CardBody className="grid gap-2">
        <p className="text-xs text-(--color-muted)">
          <Trans
            text={messages.pages.entitiesScreen.ledgerHint}
            values={{ state: <strong>{messages.pages.entitiesScreen.ledgerState}</strong> }}
          />
        </p>
        <Input
          className="max-w-xs"
          value={term}
          placeholder={messages.pages.entitiesScreen.ledgerSearchPlaceholder}
          onChange={(event) => {
            setTerm(event.target.value);
            setLimit(ENTITY_MERGE_LOG_PAGE_SIZE);
          }}
        />
        {log.isPending ? <Spinner label={messages.pages.entitiesScreen.ledgerReading} /> : null}
        {log.error ? <ErrorState error={log.error} /> : null}
        {log.data && (log.data.items ?? []).length === 0 ? (
          <EmptyState
            title={
              term.trim()
                ? fill(messages.pages.entitiesScreen.ledgerEmptyTerm, { term: term.trim() })
                : messages.pages.entitiesScreen.ledgerEmpty
            }
            hint={
              term.trim()
                ? messages.pages.entitiesScreen.ledgerEmptyTermHint
                : messages.pages.entitiesScreen.ledgerEmptyHint
            }
          />
        ) : null}
        <ul className="divide-y divide-(--color-line) text-xs">
          {(log.data?.items ?? []).map((entry) => (
            <li key={entry.merge_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              {entry.is_rename ? (
                <span className="min-w-0">
                  <span className="font-medium">{entry.canonical_renamed_from}</span>
                  <span className="text-(--color-muted)"> → {entry.canonical_name}</span>
                  <span className="text-(--color-muted)">
                    {" "}
                    {fill(messages.pages.entitiesScreen.ledgerRename, { date: formatDateTime(entry.changed_at) })}
                    {entry.changed_by
                      ? ` ${fill(messages.pages.entitiesScreen.ledgerBy, { name: entry.changed_by })}`
                      : ""}
                  </span>
                </span>
              ) : (
                <span className="min-w-0">
                  <span className="font-medium">{entry.absorbed_name}</span>
                  <span className="text-(--color-muted)"> → {entry.canonical_name}</span>
                  <span className="text-(--color-muted)">
                    {" "}
                    {fill(messages.pages.entitiesScreen.ledgerDocs, {
                      count: formatCount(entry.document_count),
                      date: formatDateTime(entry.changed_at),
                    })}
                    {entry.changed_by
                      ? ` ${fill(messages.pages.entitiesScreen.ledgerBy, { name: entry.changed_by })}`
                      : ""}
                    {entry.canonical_renamed_from
                      ? ` ${fill(messages.pages.entitiesScreen.ledgerCanonicalWas, {
                          name: entry.canonical_renamed_from,
                        })}`
                      : ""}
                  </span>
                </span>
              )}
              {entry.is_undone ? (
                <Badge tone="neutral">
                  {fill(messages.pages.entitiesScreen.ledgerUndone, { date: formatDateTime(entry.undone_at) })}
                </Badge>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={undo.isPending}
                  title={
                    entry.is_rename
                      ? messages.pages.entitiesScreen.undoRenameTitle
                      : messages.pages.entitiesScreen.undoMergeTitle
                  }
                  onClick={() => undo.mutate(entry.merge_id)}
                >
                  {ACTION.undo.label}
                </Button>
              )}
            </li>
          ))}
        </ul>
        {undo.error ? <ErrorState error={undo.error} /> : null}
        {log.data && log.data.total > (log.data.items ?? []).length ? (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => setLimit((current) => current + ENTITY_MERGE_LOG_PAGE_SIZE)}>
              {messages.pages.entitiesScreen.seeMore}
            </Button>
            <span className="text-xs text-(--color-muted)">
              {fill(messages.pages.entitiesScreen.ledgerCount, {
                shown: formatCount((log.data.items ?? []).length),
                total: formatCount(log.data.total),
              })}
            </span>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

/** Pairs by trigram, or the neighbours of one name. */
function SimilarityTab({ onMerged }: { onMerged: () => void }) {
  const [target, setTarget] = useState("");
  const [threshold, setThreshold] = useState(0.5);
  const messages = useCopy();
  /** One pair opened by its own button: the panel renders right under it. */
  const [openPair, setOpenPair] = useState<EntityPairSimilarity | null>(null);
  /** Entities marked across rows, for the case one merge has to span several pairs. */
  const [marked, setMarked] = useState<EntityCandidate[]>([]);
  const [clusterOpen, setClusterOpen] = useState(false);
  // "All pairs" answers hundreds of rows (647 at threshold 0.5 on the real vocabulary), so the list
  // starts windowed and grows on request — the same cut the tag similarity tab makes.
  const [showAll, setShowAll] = useState(false);

  const pull = useQuery(queries.similarEntities(target.trim() || undefined, threshold));

  const mode = pull.data?.mode;
  const all = pull.data?.data ?? [];
  const data = showAll ? all : all.slice(0, WINDOW);
  const pairs = mode === "specific" ? [] : (all as EntityPairSimilarity[]);

  const isMarked = (entityId: number) => marked.some((member) => member.entity_id === entityId);
  const rowMarked = (pair: EntityPairSimilarity) => isMarked(pair.id_1) && isMarked(pair.id_2);

  /**
   * A row is marked as a whole: the unit the archivist reads is the pair ("these two are the same
   * name"), and half of it is not a agrupamento. Two rows sharing a side therefore merge into three
   * entities, which is the case the pair list cannot express on its own.
   */
  const toggleRow = (pair: EntityPairSimilarity) => {
    const members: EntityCandidate[] = [
      { entity_id: pair.id_1, name: pair.name_1 },
      { entity_id: pair.id_2, name: pair.name_2 },
    ];
    setMarked((current) => {
      const already = members.every((member) => current.some((item) => item.entity_id === member.entity_id));
      if (already) return current.filter((item) => !members.some((member) => member.entity_id === item.entity_id));
      return [
        ...current,
        ...members.filter((member) => !current.some((item) => item.entity_id === member.entity_id)),
      ];
    });
  };

  const clearMarked = () => {
    setMarked([]);
    setClusterOpen(false);
  };

  const afterMerge = () => {
    clearMarked();
    setOpenPair(null);
    onMerged();
  };

  const markedRows = pairs.filter((pair) => isMarked(pair.id_1) || isMarked(pair.id_2)).length;

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label={messages.pages.entitiesScreen.similarityTargetField}>
          <Input
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder={messages.pages.entitiesScreen.similarityTargetPlaceholder}
            className="w-72"
          />
        </Field>
        <Field label={messages.pages.entitiesScreen.similarityThresholdField}>
          <Input
            type="number"
            min={0.1}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(event) => setThreshold(Number(event.target.value))}
            className="w-28"
          />
        </Field>
      </div>

      <p className="text-xs text-(--color-muted)">{messages.pages.entitiesScreen.similarityHint}</p>

      {pull.error ? <ErrorState error={pull.error} /> : null}
      {pull.isPending ? <Spinner /> : null}
      {pull.data && data.length === 0 ? (
        <EmptyState
          title={messages.pages.entitiesScreen.similarityEmptyTitle}
          hint={messages.pages.entitiesScreen.similarityEmptyHint}
        />
      ) : null}

      {/*
        More than one pair is a different operation from one pair, and it gets the panel where there is
        no single row to belong under: the top.
      */}
      {clusterOpen && marked.length >= 2 ? (
        <MergePanel
          members={marked}
          title={fill(messages.pages.entitiesScreen.mergeMarkedTitle, { count: formatCount(marked.length) })}
          hint={messages.pages.entitiesScreen.mergeMarkedHint}
          onChanged={onMerged}
          onDone={afterMerge}
          onCancel={clearMarked}
        />
      ) : null}

      {!showAll && all.length > data.length ? (
        <Button variant="secondary" onClick={() => setShowAll(true)}>
          {fill(messages.pages.entitiesScreen.showAllPairs, { count: formatCount(all.length) })}
        </Button>
      ) : null}

      <ul className="grid gap-2">
        {mode === "specific"
          ? (data as EntitySimilarity[]).map((neighbour) => (
            <li key={neighbour.entity_id}>
              <Card>
                <CardBody className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-sm">
                    <span className="font-medium">{neighbour.name}</span>
                    <Badge tone={ENTITY_TYPE_TONE[neighbour.entity_type] ?? "neutral"}>
                      {labelOf(ENTITY_TYPE_LABEL, neighbour.entity_type)}
                    </Badge>
                    <Badge tone="neutral">{neighbour.similarity.toFixed(3)}</Badge>
                  </span>
                  {/*
                      A neighbour row carries no second id: the target is the term that was typed, and
                      the answer does not include its id. Unifying needs both sides, so this list links
                      to the one that has them instead of offering a button it cannot honour.
                    */}
                  <span className="text-xs text-(--color-muted)">
                    {fill(messages.pages.entitiesScreen.neighbourHint, { target })}
                  </span>
                </CardBody>
              </Card>
            </li>
          ))
          : (data as EntityPairSimilarity[]).map((pair) => (
            <li key={`${pair.id_1}-${pair.id_2}`} className="grid gap-2">
              <Card>
                <CardBody className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={rowMarked(pair)}
                      onChange={() => toggleRow(pair)}
                      title={messages.pages.entitiesScreen.markRowTitle}
                      aria-label={fill(messages.pages.entitiesScreen.markRowAria, {
                        first: pair.name_1,
                        second: pair.name_2,
                      })}
                    />
                    <span className="font-medium">{pair.name_1}</span>
                    <span className="text-(--color-muted)">({pair.type_1})</span>
                    {/*
                        The identifiers are not decoration: the real vocabulary carries pairs whose
                        two names are *identical* ("Cia." twice, similarity 1.000), and without the
                        ids the confirmation says "mesclar Cia. → Cia." and the archivist cannot
                        tell which row is which.
                      */}
                    <code className="text-[10px] text-(--color-muted)">#{pair.id_1}</code>
                    <span className="text-(--color-muted)">≈</span>
                    <span className="font-medium">{pair.name_2}</span>
                    <span className="text-(--color-muted)">({pair.type_2})</span>
                    <code className="text-[10px] text-(--color-muted)">#{pair.id_2}</code>
                    <Badge tone="neutral">{pair.similarity.toFixed(3)}</Badge>
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setOpenPair(openPair === pair ? null : pair)}
                  >
                    {openPair === pair ? ACTION.close.label : messages.pages.entitiesScreen.mergeArrow}
                  </Button>
                </CardBody>
              </Card>
              {/*
                  In the row's own place, with the canonical choice the button never had — it used to
                  merge ``id_1`` into ``id_1`` by default and say the canonical had to be chosen "noutra
                  aba", which was the screen admitting the decision was not on it.
                */}
              {openPair === pair ? (
                <MergePanel
                  members={[
                    { entity_id: pair.id_1, name: pair.name_1 },
                    { entity_id: pair.id_2, name: pair.name_2 },
                  ]}
                  title={messages.pages.entitiesScreen.chooseCanonicalTitle}
                  hint={
                    pair.name_1 === pair.name_2 ? messages.pages.entitiesScreen.identicalNamesHint : undefined
                  }
                  onChanged={onMerged}
                  onDone={afterMerge}
                  onCancel={() => setOpenPair(null)}
                />
              ) : null}
            </li>
          ))}
      </ul>

      {marked.length >= 2 && !clusterOpen ? (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-40 flex justify-center">
          <div className="pointer-events-auto flex flex-wrap items-center gap-3 rounded-full bg-(--color-ink) px-4 py-2 text-sm text-white shadow-lg">
            <span>
              {fill(messages.pages.entitiesScreen.markedStatus, {
                count: formatCount(marked.length),
                rows: formatCount(markedRows),
              })}
            </span>
            <Button size="sm" variant="primary" onClick={() => setClusterOpen(true)}>
              {messages.pages.entitiesScreen.mergeEntities}
            </Button>
            <button className="text-xs text-white/70 hover:text-white" onClick={clearMarked}>
              {messages.pages.entitiesScreen.clearMarked}
            </button>
          </div>
        </div>
      ) : null}

      {all.length > 0 ? (
        <p className="text-xs text-(--color-muted)">
          <Trans
            text={messages.pages.entitiesScreen.seeAlso}
            values={{
              conflicts: (
                <Link to="/entidades/conflitos" className="underline">
                  {messages.pages.entitiesScreen.conflictsLink}
                </Link>
              ),
              exclusions: (
                <Link to="/entidades/excecoes" className="underline">
                  {messages.screens.nerExclusions.label}
                </Link>
              ),
            }}
          />
        </p>
      ) : null}
    </div>
  );
}


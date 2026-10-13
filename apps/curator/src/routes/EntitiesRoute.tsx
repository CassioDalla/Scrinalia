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
 * The two questions one entity card answers: what carries this name, and what it is called.
 *
 * The same pair the category card has, and deliberately the same shape — one body, not two, because
 * the pencil beside the name and the expansion under it are one object being read and corrected.
 */
const ENTITY_CARD_TABS = [
  { id: "descricoes", label: "Descrições" },
  { id: "editar", label: "Editar" },
];

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
            ? `${formatCount(rows.length)} nomes por relvância · ${formatCount(
              rows.reduce((sum, row) => sum + row.total_usage, 0),
            )} vínculos entre os listados`
            : undefined
        }
        actions={
          <Button
            size="sm"
            variant="danger"
            disabled={purgeOrphans.isPending}
            title="Exclui as entidades que nenhuma descrição carrega"
            onClick={() => purgeOrphans.mutate()}
          >
            {purgeOrphans.isPending ? ACTION.exclude.pending : "Excluir Órfãs"}
          </Button>
        }
      />

      <PageBody>
        <Notice tone="accent">
          <strong>Reclassificar não é renomear um rótulo.</strong> Ao corrigir o tipo, o serviço grava
          também o sinônimo de ancoragem: o extrator passa a devolver aquela grafia com o tipo novo, em
          toda execução futura. E <strong>mesclar tem desfazer</strong>: cada entidade absorvida entra no
          ledger antes de a escrita acontecer, e o painel mostra o impacto antes do clique.
        </Notice>

        {purgeOrphans.data ? (
          <p className="text-xs text-(--color-muted)">
            {routeMessage(purgeOrphans.data)} {formatCount(purgeOrphans.data.entities_deleted)} excluídas.
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
            { id: "relevancia", label: "Relevância" },
            { id: "similaridade", label: "Similaridade" },
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
                Todos os tipos
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
                  {formatCount(selected.length)} selecionada(s) · marque ao menos duas para mesclar
                </span>
              ) : (
                <span className="text-xs text-(--color-muted)">
                  Marque duas ou mais para mesclar; o tipo se corrige na própria linha.
                </span>
              )}
            </div>

            {relevance.error ? <ErrorState error={relevance.error} /> : null}
            {relevance.isPending ? <Spinner /> : null}
            {relevance.data && rows.length === 0 ? (
              <EmptyState
                title="Nenhuma entidade neste tipo"
                hint="A extração de nomes ainda não rodou neste acervo, ou o filtro escolhido não tem nomes. O worker de NER é quem popula esta lista."
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
        toggleLabel={`Ver as descrições de ${entity.name}`}
        header={
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium">{entity.name}</span>
            <Badge tone={ENTITY_TYPE_TONE[entity.entity_type] ?? "neutral"}>
              {labelOf(ENTITY_TYPE_LABEL, entity.entity_type)}
            </Badge>
            <Badge tone="neutral" title="Descrições que carregam este nome">
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
              aria-label={`Selecionar ${entity.name}`}
            />
            <label className="flex items-center gap-1 text-xs text-(--color-muted)">
              tipo
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
              title="Corrigir a grafia deste nome, sem mesclar com outra entidade"
              aria-label={`Renomear ${entity.name}`}
              onClick={openRename}
            >
              {ACTION.rename.label}
            </Button>

            {orphan ? (
              <Button
                size="sm"
                variant="danger"
                disabled={remove.isPending}
                title="Nenhuma descrição carrega este nome: excluir não perde vínculo"
                onClick={() => remove.mutate()}
              >
                {ACTION.exclude.label}
              </Button>
            ) : null}
          </div>
        }
      >
        <div className="grid gap-3">
          <Tabs items={ENTITY_CARD_TABS} active={tab} onChange={setTab} />

          {tab === "editar" ? (
            <div className="grid gap-2">
              <Field label="Nome">
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
                <span>
                  manter a grafia antiga como sinônimo — é o que faz uma extração futura da grafia
                  antiga continuar resolvendo para esta entidade. Desmarque quando a grafia antiga for
                  um erro de digitação.
                </span>
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
                {dirty ? <span className="text-xs text-(--color-muted)">alteração não salva</span> : null}
              </div>

              {rename.data ? (
                <p className="text-xs text-(--color-muted)">
                  {routeMessage(rename.data)}{" "}
                  {rename.data.kept_old_spelling
                    ? `A grafia antiga continua resolvendo para esta entidade, e o desfazer é a linha ${rename.data.merge_id} do ledger.`
                    : `A grafia antiga não foi mantida, e o desfazer é a linha ${rename.data.merge_id} do ledger.`}
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
                title: "Nenhuma descrição carrega este nome",
                hint: "O nome existe no vocabulário e nenhuma descrição o carrega — é a linha que a exclusão de órfãs remove. A expansão lê a mesma busca da lista, então o número aqui é o mesmo do cartão.",
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
      triggerLabel="+ Mesclar pelo nome"
      toggleLabel="Mesclar duas entidades escritas pelo nome"
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">Mesclar pelo nome</span>
          <span className="text-xs text-(--color-muted)">
            Para o par que nenhuma lista aproxima: escreva as duas grafias e mescle. As caixas marcadas
            na aba Relevância não entram aqui.
          </span>
        </div>
      }
    >
      <div className="grid gap-3">
        <Typeahead
          placeholder="digite ao menos 2 letras: smu…"
          emptyLabel="nenhuma entidade com esse trecho"
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
          <p className="text-xs text-(--color-muted)">
            Nenhum nome escolhido ainda. Escreva as duas grafias que você já sabe que são uma só.
          </p>
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
          <p className="text-xs text-(--color-muted)">
            Um merge precisa de duas grafias, e abaixo disso nada é escrito.
          </p>
        ) : (
          <MergePanel
            members={members}
            title="Mesclar os nomes escolhidos"
            hint="A canônica é escolha sua. O desfazer de cada entidade absorvida fica no ledger, no fim desta tela."
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
        <p className="text-sm font-semibold">{title ?? `Mesclar ${formatCount(members.length)} entidades`}</p>
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
                {canonicalId === member.entity_id ? " — mantida (canônica)" : " — absorvida"}
              </span>
            </label>
          ))}
        </div>

        <Field label="Renomear a canônica (opcional; o nome antigo vira sinônimo)">
          <Input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder={nameOf(canonicalId)}
            className="max-w-md"
          />
        </Field>

        {/* The dry run, before the click: the same planner the merge executes computes these. */}
        {preview.isPending ? <Spinner label="Calculando o impacto…" /> : null}
        {preview.error ? <ErrorState error={preview.error} /> : null}
        {preview.data ? (
          <p className="text-xs text-(--color-muted)">
            {formatCount(preview.data.documents_updated)} descrição(ões) passam a carregar{" "}
            <strong>{nameOf(canonicalId)}</strong> · {formatCount(preview.data.links_rewritten)} vínculo(s)
            reescrito(s) · {formatCount(preview.data.entities_deleted?.length ?? 0)} entidade(s) absorvida(s).
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
          As <strong>{formatCount(absorbed.length)}</strong> entidades absorvidas deixam de existir e
          seus vínculos passam para <strong>{nameOf(canonicalId)}</strong>. As grafias viram sinônimos
          (o extrator continua reconhecendo-as) e cada absorvida entra no ledger{" "}
          <strong>antes</strong> da escrita — o desfazer restaura a linha, os vínculos e as grafias.
        </Notice>

        <div className="flex items-center gap-2">
          <Button variant="primary" disabled={merge.isPending || absorbed.length === 0} onClick={() => merge.mutate()}>
            {merge.isPending
              ? ACTION.merge.pending
              : absorbed.length === 1
                ? `Mesclar ${absorbed[0]?.name} em ${nameOf(canonicalId)}`
                : `Mesclar ${formatCount(absorbed.length)} nomes em ${nameOf(canonicalId)}`}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            {ACTION.cancel.label}
          </Button>
        </div>

        {merge.data ? (
          <div className="grid gap-1 text-xs text-(--color-muted)">
            <p>
              {formatCount(merge.data.documents_updated)} vínculo(s) movido(s) ·{" "}
              {formatCount(merge.data.entities_deleted)} entidade(s) absorvida(s) · ledger{" "}
              <code>{(merge.data.merge_ids ?? []).join(", ") || "—"}</code>.
            </p>
            {(merge.data.merge_ids ?? []).length > 0 ? (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={undo.isPending}
                  title="Restaura cada entidade absorvida, seus vínculos e as grafias."
                  onClick={() => undo.mutate(merge.data.merge_ids ?? [])}
                >
                  {undo.isPending ? "desfazendo…" : "Desfazer este merge"}
                </Button>
                <span>O desfazer também está no ledger abaixo.</span>
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

  const log = useQuery(queries.entityMergeLog(limit, term.trim() || undefined));

  const undo = useMutation({
    mutationFn: (mergeId: number) => undoEntityMerge(mergeId),
    onSuccess: onChanged,
  });

  return (
    <Card>
      <CardHeader className="text-sm font-semibold">Ledger dos nomes: merges e renomeações</CardHeader>
      <CardBody className="grid gap-2">
        <p className="text-xs text-(--color-muted)">
          Aqui só entram escritas <strong>aplicadas</strong>. Cada linha guarda o estado anterior — no
          merge, a entidade, seus vínculos, suas grafias e o nome que a canônica perdeu; na
          renomeação, o nome antigo e se ele ficou como sinônimo — e o desfazer restaura tudo.
        </p>
        <Input
          className="max-w-xs"
          value={term}
          placeholder="buscar por grafia absorvida ou canônica…"
          onChange={(event) => {
            setTerm(event.target.value);
            setLimit(ENTITY_MERGE_LOG_PAGE_SIZE);
          }}
        />
        {log.isPending ? <Spinner label="Lendo o ledger…" /> : null}
        {log.error ? <ErrorState error={log.error} /> : null}
        {log.data && (log.data.items ?? []).length === 0 ? (
          <EmptyState
            title={term.trim() ? `Nenhum registro para “${term.trim()}”` : "Nenhuma decisão sobre nomes ainda"}
            hint={
              term.trim()
                ? "A busca cobre as duas grafias de cada linha: a absorvida (ou a antiga) e a canônica."
                : "O ledger registra cada entidade absorvida por um merge e cada nome renomeado, com o antes."
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
                    · renomeação · {formatDateTime(entry.changed_at)}
                    {entry.changed_by ? ` · por ${entry.changed_by}` : ""}
                  </span>
                </span>
              ) : (
                <span className="min-w-0">
                  <span className="font-medium">{entry.absorbed_name}</span>
                  <span className="text-(--color-muted)"> → {entry.canonical_name}</span>
                  <span className="text-(--color-muted)">
                    {" "}
                    · {formatCount(entry.document_count)} doc(s) · {formatDateTime(entry.changed_at)}
                    {entry.changed_by ? ` · por ${entry.changed_by}` : ""}
                    {entry.canonical_renamed_from ? ` · canônica era “${entry.canonical_renamed_from}”` : ""}
                  </span>
                </span>
              )}
              {entry.is_undone ? (
                <Badge tone="neutral">desfeito em {formatDateTime(entry.undone_at)}</Badge>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={undo.isPending}
                  title={
                    entry.is_rename
                      ? "Devolve o nome anterior e desfaz o sinônimo que a renomeação plantou."
                      : "Restaura a entidade, seus vínculos, suas grafias e o nome da canônica."
                  }
                  onClick={() => undo.mutate(entry.merge_id)}
                >
                  desfazer
                </Button>
              )}
            </li>
          ))}
        </ul>
        {undo.error ? <ErrorState error={undo.error} /> : null}
        {log.data && log.data.total > (log.data.items ?? []).length ? (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => setLimit((current) => current + ENTITY_MERGE_LOG_PAGE_SIZE)}>
              ver mais
            </Button>
            <span className="text-xs text-(--color-muted)">
              {formatCount((log.data.items ?? []).length)} de {formatCount(log.data.total)}
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
        <Field label="Nome-alvo (vazio = todos os pares parecidos)">
          <Input
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder="ex.: prefeitura"
            className="w-72"
          />
        </Field>
        <Field label="Limiar de similaridade">
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

      <p className="text-xs text-(--color-muted)">
        O par é evidência, não decisão: similaridade de trigrama alta também acontece entre nomes
        diferentes. A canônica é escolha sua, e mesclar aqui é a mesma operação da aba de relevância —
        o ledger guarda cada absorvida e o desfazer restaura. Para mesclar mais de um par de uma vez,
        marque as linhas e use a barra que aparece embaixo.
      </p>

      {pull.error ? <ErrorState error={pull.error} /> : null}
      {pull.isPending ? <Spinner /> : null}
      {pull.data && data.length === 0 ? (
        <EmptyState
          title="Nenhum par acima do limiar"
          hint="Com o limiar assim e nenhum par, o vocabulário pode já estar limpo — ou o alvo não existe."
        />
      ) : null}

      {/*
        More than one pair is a different operation from one pair, and it gets the panel where there is
        no single row to belong under: the top.
      */}
      {clusterOpen && marked.length >= 2 ? (
        <MergePanel
          members={marked}
          title={`Mesclar ${formatCount(marked.length)} entidades marcadas`}
          hint="Estas entidades vieram de linhas diferentes da lista: a canônica é escolhida abaixo. O ledger guarda cada absorvida e o desfazer restaura."
          onChanged={onMerged}
          onDone={afterMerge}
          onCancel={clearMarked}
        />
      ) : null}

      {!showAll && all.length > data.length ? (
        <Button variant="secondary" onClick={() => setShowAll(true)}>
          mostrar todos os {formatCount(all.length)} pares
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
                    vizinho de “{target}” — para mesclar, abra a lista de pares (esta resposta não traz o
                    id do alvo)
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
                      title="Marcar as duas entidades desta linha para mesclar em conjunto"
                      aria-label={`Marcar ${pair.name_1} e ${pair.name_2}`}
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
                    {openPair === pair ? ACTION.close.label : "Mesclar ↦"}
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
                  title="Escolher a canônica e mesclar"
                  hint={
                    pair.name_1 === pair.name_2
                      ? "Os dois nomes são idênticos nesta linha: confira os identificadores antes de decidir."
                      : undefined
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
              {formatCount(marked.length)} entidades marcadas em {formatCount(markedRows)} linha(s)
            </span>
            <Button size="sm" variant="primary" onClick={() => setClusterOpen(true)}>
              Mesclar entidades
            </Button>
            <button className="text-xs text-white/70 hover:text-white" onClick={clearMarked}>
              limpar
            </button>
          </div>
        </div>
      ) : null}

      {all.length > 0 ? (
        <p className="text-xs text-(--color-muted)">
          Veja também os <Link to="/entidades/conflitos" className="underline">conflitos com o eixo de assunto</Link>{" "}
          e as <Link to="/entidades/excecoes" className="underline">exclusões de NER</Link>.
        </p>
      ) : null}
    </div>
  );
}


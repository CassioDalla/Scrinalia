import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  deleteEntity,
  mergeEntities,
  purgeOrphanEntities,
  reclassifyEntity,
  type EntityPairSimilarity,
  type EntityRelevance,
  type EntitySimilarity,
  type EntityType,
  type ReclassifyTarget,
} from "@/api/client";
import { queries, RELEVANCE_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { ENTITY_TYPE_HINT, ENTITY_TYPE_LABEL, ENTITY_TYPE_TONE } from "@/lib/entities";
import { descricoes, formatCount } from "@/lib/format";
import { asEnum, asNumber } from "@/lib/search";
import { labelOf } from "@/lib/hierarchy";
import { routeMessage } from "@/lib/messages";

const routeApi = getRouteApi("/entidades/lista");

export type EntitiesSearch = { aba?: "relevancia" | "similaridade"; tipo?: EntityType; limiar?: number };

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
  };
}

/** How many similarity rows are drawn before the archivist asks for the rest. */
const WINDOW = 100;

/**
 * The named-entity vocabulary.
 *
 * The screen exists to make one thing unmistakable: **reclassifying teaches the extractor**, and
 * **merging has no undo**. Nothing here keeps a ledger — that is the tags' privilege — so the merge
 * carries a warning instead of an undo button, and the delete is offered only where the API's own
 * intent fits: an entity no description carries.
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
        title="Entidades nomeadas"
        subtitle={
          relevance.data
            ? `${formatCount(rows.length)} nomes por peso · ${formatCount(
                rows.reduce((sum, row) => sum + row.total_usage, 0),
              )} vínculos entre os listados`
            : "Lendo o vocabulário de nomes…"
        }
        actions={
          <Button
            size="sm"
            variant="danger"
            disabled={purgeOrphans.isPending}
            title="Apaga as entidades que nenhuma descrição carrega"
            onClick={() => purgeOrphans.mutate()}
          >
            {purgeOrphans.isPending ? "Purgando…" : "Purgar órfãs"}
          </Button>
        }
      />

      <div className="grid max-w-6xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-accent)/5 px-3 py-2 text-xs text-(--color-accent) ring-1 ring-(--color-accent)/20">
          <strong>Reclassificar não é renomear um rótulo.</strong> Ao corrigir o tipo, o serviço grava
          também o sinônimo de ancoragem: o extrator passa a devolver aquela grafia com o tipo novo, em
          toda execução futura. E <strong>unificar não tem desfazer</strong> — só as tags têm ledger; a
          entidade absorvida vira sinônimo e não volta.
        </p>

        {purgeOrphans.data ? (
          <p className="text-xs text-(--color-muted)">
            {routeMessage(purgeOrphans.data)} {formatCount(purgeOrphans.data.entities_deleted)} removidas.
          </p>
        ) : null}
        {purgeOrphans.error ? <ErrorState error={purgeOrphans.error} /> : null}

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
                  {formatCount(selected.length)} selecionada(s) · marque ao menos duas para unificar
                </span>
              ) : (
                <span className="text-xs text-(--color-muted)">
                  Marque duas ou mais para unificar; o tipo se corrige na própria linha.
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
                  onToggle={() => toggle(row.entity_id)}
                  onChanged={invalidate}
                />
              ))}
            </ul>
          </>
        ) : (
          <SimilarityTab onMerged={invalidate} />
        )}
      </div>
    </>
  );
}

/** One entity by weight, with the type correction and the delete where it is honest to offer it. */
function EntityRow({
  entity,
  checked,
  onToggle,
  onChanged,
}: {
  entity: EntityRelevance;
  checked: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const reclassify = useMutation({
    mutationFn: (newType: ReclassifyTarget) => reclassifyEntity(entity.entity_id, { new_type: newType }),
    onSuccess: onChanged,
  });

  const remove = useMutation({
    mutationFn: () => deleteEntity(entity.entity_id),
    onSuccess: onChanged,
  });

  const orphan = entity.total_usage === 0;

  return (
    <li>
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <input
              type="checkbox"
              checked={checked}
              onChange={onToggle}
              aria-label={`Selecionar ${entity.name}`}
            />
            <span className="truncate text-sm font-medium">{entity.name}</span>
            <Badge tone={ENTITY_TYPE_TONE[entity.entity_type] ?? "neutral"}>
              {labelOf(ENTITY_TYPE_LABEL, entity.entity_type)}
            </Badge>
            <Badge tone="neutral" title="Descrições que carregam este nome">
              {descricoes(entity.total_usage)}
            </Badge>
          </div>

          <div className="flex flex-wrap items-center gap-2">
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

            {orphan ? (
              <Button
                size="sm"
                variant="danger"
                disabled={remove.isPending}
                title="Nenhuma descrição carrega este nome: apagar não perde vínculo"
                onClick={() => remove.mutate()}
              >
                excluir
              </Button>
            ) : null}
          </div>
        </CardBody>
        {reclassify.error ? <ErrorState error={reclassify.error} /> : null}
        {remove.error ? <ErrorState error={remove.error} /> : null}
      </Card>
    </li>
  );
}

/**
 * The confirmation step of a merge, and the only place the effect is stated.
 *
 * There is no entity preview route — the tag merge has ``plan_merge`` and this one does not — so the
 * screen states the documented effect instead of inventing numbers: the documents move to the
 * canonical, the absorbed names become synonyms, and the rows disappear. Warning instead of an undo,
 * because there is none.
 */
function MergePanel({
  members,
  title,
  hint,
  onDone,
  onCancel,
}: {
  members: EntityCandidate[];
  title?: string;
  hint?: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [canonicalId, setCanonicalId] = useState(members[0]?.entity_id ?? 0);
  const [newName, setNewName] = useState("");
  const nameOf = (id: number) => members.find((member) => member.entity_id === id)?.name ?? `#${id}`;

  const merge = useMutation({
    mutationFn: () =>
      mergeEntities({
        canonical_id: canonicalId,
        ids_to_merge: members.map((member) => member.entity_id).filter((id) => id !== canonicalId),
        new_name: newName.trim() || null,
      }),
    onSuccess: onDone,
  });

  const absorbed = members.filter((member) => member.entity_id !== canonicalId);

  return (
    <Card className="ring-(--color-warn)/40">
      <CardBody className="grid gap-3">
        <p className="text-sm font-semibold">{title ?? `Unificar ${formatCount(members.length)} entidades`}</p>
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

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Renomear a canônica (opcional; o nome antigo vira sinônimo)</span>
          <Input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder={nameOf(canonicalId)}
            className="max-w-md"
          />
        </label>

        <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
          As <strong>{formatCount(absorbed.length)}</strong> entidades absorvidas deixam de existir e
          seus vínculos passam para <strong>{nameOf(canonicalId)}</strong>. As grafias viram sinônimos
          (o extrator continua reconhecendo-as) — mas <strong>não há desfazer</strong>: entidades não
          têm ledger como as tags.
        </p>

        <div className="flex items-center gap-2">
          <Button variant="primary" disabled={merge.isPending} onClick={() => merge.mutate()}>
            {merge.isPending
              ? "Unificando…"
              : absorbed.length === 1
                ? `Unificar ${absorbed[0]?.name} em ${nameOf(canonicalId)}`
                : `Unificar ${formatCount(absorbed.length)} nomes em ${nameOf(canonicalId)}`}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            cancelar
          </Button>
        </div>
        {merge.data ? (
          <p className="text-xs text-(--color-muted)">
            {formatCount(merge.data.documents_updated)} vínculos movidos ·{" "}
            {formatCount(merge.data.entities_deleted)} entidades absorvidas.
          </p>
        ) : null}
        {merge.error ? <ErrorState error={merge.error} /> : null}
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
   * name"), and half of it is not a cluster. Two rows sharing a side therefore merge into three
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
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Nome-alvo (vazio = todos os pares parecidos)</span>
          <Input
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder="ex.: prefeitura"
            className="w-72"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Limiar de similaridade</span>
          <Input
            type="number"
            min={0.1}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(event) => setThreshold(Number(event.target.value))}
            className="w-28"
          />
        </label>
      </div>

      <p className="text-xs text-(--color-muted)">
        O par é evidência, não decisão: similaridade de trigrama alta também acontece entre nomes
        diferentes. A canônica é escolha sua, e unificar aqui é a mesma operação irreversível da aba de
        relevância — só as tags têm ledger. Para juntar mais de um par de uma vez, marque as linhas e use
        a barra que aparece embaixo.
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
          title={`Unificar ${formatCount(marked.length)} entidades marcadas`}
          hint="Estas entidades vieram de linhas diferentes da lista: a canônica é escolhida abaixo. Não há desfazer — entidades não têm ledger como as tags."
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
                      vizinho de “{target}” — para unificar, abra a lista de pares (esta resposta não traz o
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
                        title="Marcar as duas entidades desta linha para unificar em conjunto"
                        aria-label={`Marcar ${pair.name_1} e ${pair.name_2}`}
                      />
                      <span className="font-medium">{pair.name_1}</span>
                      <span className="text-(--color-muted)">({pair.type_1})</span>
                      {/*
                        The identifiers are not decoration: the real vocabulary carries pairs whose
                        two names are *identical* ("Cia." twice, similarity 1.000), and without the
                        ids the confirmation says "unificar Cia. → Cia." and the archivist cannot
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
                      {openPair === pair ? "fechar" : "unificar ↦"}
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
                    title="Escolher a canônica e unificar"
                    hint={
                      pair.name_1 === pair.name_2
                        ? "Os dois nomes são idênticos nesta linha: confira os identificadores antes de decidir."
                        : undefined
                    }
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


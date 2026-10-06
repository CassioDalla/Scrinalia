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

const routeApi = getRouteApi("/entidades/lista");

export type EntitiesSearch = { aba?: "relevancia" | "similaridade"; tipo?: EntityType; limiar?: number };

const TYPE_VALUES: ReclassifyTarget[] = ["ORG", "PER", "LOC"];

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
  const [canonicalId, setCanonicalId] = useState<number | null>(null);
  const [newName, setNewName] = useState("");

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
    setSelected((current) => {
      const next = current.includes(entityId)
        ? current.filter((id) => id !== entityId)
        : [...current, entityId];
      if (canonicalId !== null && !next.includes(canonicalId)) setCanonicalId(next[0] ?? null);
      return next;
    });

  const nameOf = (entityId: number) => rows.find((row) => row.entity_id === entityId)?.name ?? `#${entityId}`;

  const clear = () => {
    setSelected([]);
    setCanonicalId(null);
    setNewName("");
  };

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
            {purgeOrphans.data.message} {formatCount(purgeOrphans.data.entities_deleted)} removidas.
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
            selected={selected}
            // The panel only renders with two or more selected, so the first one exists; the
            // fallback keeps the type checker honest about the index.
            canonicalId={canonicalId ?? selected[0] ?? 0}
            nameOf={nameOf}
            newName={newName}
            onCanonical={setCanonicalId}
            onNewName={setNewName}
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
  selected,
  canonicalId,
  nameOf,
  newName,
  onCanonical,
  onNewName,
  onDone,
  onCancel,
}: {
  selected: number[];
  canonicalId: number;
  nameOf: (id: number) => string;
  newName: string;
  onCanonical: (id: number) => void;
  onNewName: (name: string) => void;
  onDone: () => void;
  onCancel: () => void;
}) {
  const merge = useMutation({
    mutationFn: () =>
      mergeEntities({
        canonical_id: canonicalId,
        ids_to_merge: selected.filter((id) => id !== canonicalId),
        new_name: newName.trim() || null,
        changed_by: null,
      }),
    onSuccess: onDone,
  });

  const absorbed = selected.filter((id) => id !== canonicalId);

  return (
    <Card className="ring-(--color-warn)/40">
      <CardBody className="grid gap-3">
        <p className="text-sm font-semibold">Unificar {formatCount(selected.length)} entidades</p>

        <div className="grid gap-2 text-xs">
          {selected.map((entityId) => (
            <label key={entityId} className="flex items-center gap-2">
              <input
                type="radio"
                name="canonical"
                checked={canonicalId === entityId}
                onChange={() => onCanonical(entityId)}
              />
              <span className={canonicalId === entityId ? "font-medium" : "text-(--color-muted)"}>
                {nameOf(entityId)}
                {canonicalId === entityId ? " — mantida (canônica)" : " — absorvida"}
              </span>
            </label>
          ))}
        </div>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Renomear a canônica (opcional; o nome antigo vira sinônimo)</span>
          <Input
            value={newName}
            onChange={(event) => onNewName(event.target.value)}
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
            {merge.isPending ? "Unificando…" : "Unificar"}
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
  const [pending, setPending] = useState<{ canonical: number; absorbed: number; label: string } | null>(null);
  // "All pairs" answers hundreds of rows (647 at threshold 0.5 on the real vocabulary), so the list
  // starts windowed and grows on request — the same cut the tag similarity tab makes.
  const [showAll, setShowAll] = useState(false);

  const pull = useQuery(queries.similarEntities(target.trim() || undefined, threshold));

  const merge = useMutation({
    mutationFn: (pair: { canonical: number; absorbed: number }) =>
      mergeEntities({ canonical_id: pair.canonical, ids_to_merge: [pair.absorbed], new_name: null, changed_by: null }),
    onSuccess: () => {
      setPending(null);
      onMerged();
    },
  });

  const mode = pull.data?.mode;
  const all = pull.data?.data ?? [];
  const data = showAll ? all : all.slice(0, WINDOW);

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
        O par é evidência, não decisão: similaridade de trigrama alta também acontece entre coisas
        diferentes. Unificar aqui é a mesma operação irreversível da aba de relevância.
      </p>

      {pull.error ? <ErrorState error={pull.error} /> : null}
      {pull.isPending ? <Spinner /> : null}
      {pull.data && data.length === 0 ? (
        <EmptyState
          title="Nenhum par acima do limiar"
          hint="Com o limiar assim e nenhum par, o vocabulário pode já estar limpo — ou o alvo não existe."
        />
      ) : null}

      {pending ? (
        <Card className="ring-(--color-warn)/40">
          <CardBody className="grid gap-2">
            <p className="text-sm">
              Unificar <strong>{pending.label}</strong>?
            </p>
            <p className="text-xs text-(--color-warn)">
              A entidade absorvida deixa de existir e a grafia vira sinônimo. Não há desfazer.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="primary"
                disabled={merge.isPending}
                onClick={() => merge.mutate({ canonical: pending.canonical, absorbed: pending.absorbed })}
              >
                {merge.isPending ? "Unificando…" : "Confirmar"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setPending(null)}>
                cancelar
              </Button>
            </div>
            {merge.error ? <ErrorState error={merge.error} /> : null}
          </CardBody>
        </Card>
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
                    <span className="text-xs text-(--color-muted)">
                      vizinho de “{target}” — a unificação teria de escolher a canônica noutra aba
                    </span>
                  </CardBody>
                </Card>
              </li>
            ))
          : (data as EntityPairSimilarity[]).map((pair) => (
              <li key={`${pair.id_1}-${pair.id_2}`}>
                <Card>
                  <CardBody className="flex flex-wrap items-center justify-between gap-2">
                    <span className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
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
                      onClick={() =>
                        setPending({
                          canonical: pair.id_1,
                          absorbed: pair.id_2,
                          label: `${pair.name_2} #${pair.id_2} → ${pair.name_1} #${pair.id_1}`,
                        })
                      }
                    >
                      unificar ↦
                    </Button>
                  </CardBody>
                </Card>
              </li>
            ))}
      </ul>

      {pull.data && all.length === 0 ? null : (
        <p className="text-xs text-(--color-muted)">
          Veja também os <Link to="/entidades/conflitos" className="underline">conflitos com o eixo de assunto</Link>{" "}
          e as <Link to="/entidades/excecoes" className="underline">exclusões de NER</Link>.
        </p>
      )}
    </div>
  );
}

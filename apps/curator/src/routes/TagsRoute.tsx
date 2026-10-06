import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  applyMergeBatch,
  banStopwords,
  fetchMergeProposals,
  decideMergeProposal,
  mergeTags,
  previewMerge,
  previewStopwordPurge,
  previewTagPair,
  purgeStopwords,
  suggestMergeProposals,
  unbanStopwords,
  undoMerge,
  type BatchMergeResponse,
  type MergePreview,
  type MergeReason,
  type MergeResponse,
  type ProposalStatus,
  type StopwordPurgePreview,
  type StopwordsScope,
  type TagMergeProposal,
  type TagPairSimilarity,
} from "@/api/client";
import { queries, MERGE_LOG_PAGE_SIZE, PROPOSALS_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { formatCount, formatDateTime } from "@/lib/format";
import { asBoolean, asEnum, asNumber, asString } from "@/lib/search";
import {
  MERGE_REASON_LABEL,
  MERGE_REASON_TONE,
  PROPOSAL_STATUS_LABEL,
  PROPOSAL_STATUS_TONE,
  REVIEW_FLAG_HINT,
  REVIEW_FLAG_LABEL,
  STOPWORD_SCOPE_HINT,
  STOPWORD_SCOPE_LABEL,
  labelOf,
} from "@/lib/taxonomy";

const routeApi = getRouteApi("/assuntos/tags");

const TABS = [
  { id: "relevancia", label: "Relevância" },
  { id: "similaridade", label: "Similaridade" },
  { id: "propostas", label: "Propostas de merge" },
  { id: "stopwords", label: "Stopwords" },
];

const REASONS: MergeReason[] = ["TRIGRAM", "PLURAL", "MIXED"];
const SCOPE_VALUES: StopwordsScope[] = ["TAG", "ENTITY", "ALL"];

/** Mirrors ``MAX_MERGE_BATCH_CLUSTERS``: the API refuses a bigger batch, so the screen does not send one. */
const MAX_BATCH = 200;
const STATUSES: ProposalStatus[] = ["SUGGESTED", "APPROVED", "REJECTED", "APPLIED"];

export type TagsSearch = {
  aba?: string;
  metodo?: "count" | "tfidf";
  limiar?: number;
  alvo?: string;
  nome?: string;
  status?: ProposalStatus;
  motivo?: MergeReason;
  min?: number;
  flag?: boolean;
  offset?: number;
  escopo?: StopwordsScope;
};

export function validateTagsSearch(search: Record<string, unknown>): TagsSearch {
  return {
    aba: asEnum(search.aba, TABS.map((tab) => tab.id)) ?? "relevancia",
    metodo: asEnum(search.metodo, ["count", "tfidf"]) ?? "count",
    limiar: asNumber(search.limiar) ?? 0.65,
    alvo: asString(search.alvo),
    nome: asString(search.nome),
    status: asEnum(search.status, STATUSES),
    motivo: asEnum(search.motivo, REASONS),
    min: asNumber(search.min),
    flag: asBoolean(search.flag),
    offset: asNumber(search.offset),
    escopo: asEnum(search.escopo, SCOPE_VALUES),
  };
}

/**
 * The tag catalog: what weighs most, what looks duplicated, and the queue of merge decisions.
 *
 * The three questions live in one route because they are one conversation — the archivist sees that
 * ``alvenarias`` weighs little, finds its near-duplicate, and decides whether to absorb it. The
 * active question is in the URL, so a colleague can be sent the exact list.
 *
 * The stopwords subtab manages the banned terms **and** the one destructive write in the taxonomy
 * that has no undo. Banning and purging are separate steps on purpose: banning a word deletes
 * nothing, and the purge shows what it would destroy before destroying it.
 */
export function TagsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  /**
   * The URL is the state, as everywhere else.
   *
   * ``offset: changes.offset`` and not ``offset: undefined``: a filter change has to return to the
   * first page — page 3 of the previous filter means nothing — but the pagination of the proposals
   * tab goes through this same function, and the unconditional reset silently threw its page number
   * away, so "Próxima" reloaded page 1 forever.
   */
  const patch = (changes: Partial<TagsSearch>) =>
    navigate({ to: "/assuntos/tags", search: { ...search, ...changes, offset: changes.offset } });

  return (
    <>
      <PageHeader
        title="Vocabulário de tags"
        subtitle="Peso, duplicatas e a fila de merges — a decisão é sempre sua, e o merge é reversível."
      />

      <div className="px-6">
        <Tabs
          items={TABS}
          active={search.aba ?? "relevancia"}
          onChange={(id) => patch({ aba: id })}
        />
      </div>

      <div className="px-6 py-5">
        {search.aba === "similaridade" ? (
          <SimilarityTab search={search} patch={patch} />
        ) : search.aba === "propostas" ? (
          <ProposalsTab search={search} patch={patch} />
        ) : search.aba === "stopwords" ? (
          <StopwordsTab search={search} patch={patch} />
        ) : (
          <RelevanceTab search={search} patch={patch} />
        )}
      </div>
    </>
  );
}

// =============================================================================================
// Relevância
// =============================================================================================

function RelevanceTab({
  search,
  patch,
}: {
  search: TagsSearch;
  patch: (changes: Partial<TagsSearch>) => void;
}) {
  const method = search.metodo ?? "count";
  const [limit, setLimit] = useState(30);
  const relevance = useQuery(queries.tagRelevance(method, limit));

  const payload = relevance.data?.payload ?? [];

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select className="w-48" value={method} onChange={(event) => patch({ metodo: event.target.value as "count" | "tfidf" })}>
          <option value="count">Contagem de uso</option>
          <option value="tfidf">TF-IDF (pune o genérico)</option>
        </Select>
        <Select className="w-36" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
          {[30, 50, 100, 200].map((value) => (
            <option key={value} value={value}>
              {value} tags
            </option>
          ))}
        </Select>
      </div>

      <p className="max-w-3xl text-xs text-(--color-muted)">
        A contagem mostra o que pesa no acervo; o TF-IDF mostra o que é específico, punindo o que aparece em toda
        parte. As duas listas respondem perguntas diferentes de propósito — a primeira acha o que dominar, a segunda
        o que caracteriza.
      </p>

      {relevance.error ? <ErrorState error={relevance.error} /> : null}
      {relevance.isPending ? <Spinner /> : null}

      {payload.length > 0 ? (
        <Card>
          <CardBody className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-(--color-line) text-xs text-(--color-muted)">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Tag</th>
                  {method === "count" ? (
                    <th className="px-3 py-2 text-right font-medium">Documentos</th>
                  ) : (
                    <>
                      <th className="px-3 py-2 text-right font-medium">Frequência</th>
                      <th className="px-3 py-2 text-right font-medium">IDF</th>
                      <th className="px-3 py-2 text-right font-medium">TF-IDF</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {payload.map((row) => (
                  <tr key={row.name} className="border-b border-(--color-line) last:border-b-0">
                    <td className="px-3 py-1.5">{row.name}</td>
                    {"total_usage" in row ? (
                      <td className="px-3 py-1.5 text-right tabular-nums">{formatCount(row.total_usage)}</td>
                    ) : (
                      <>
                        <td className="px-3 py-1.5 text-right tabular-nums">{formatCount(row.frequency)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{row.weight_idf.toFixed(2)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{row.score_tfidf.toFixed(2)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

// =============================================================================================
// Similaridade
// =============================================================================================

function SimilarityTab({
  search,
  patch,
}: {
  search: TagsSearch;
  patch: (changes: Partial<TagsSearch>) => void;
}) {
  const queryClient = useQueryClient();
  const threshold = search.limiar ?? 0.65;
  const [showAll, setShowAll] = useState(false);
  const [pending, setPending] = useState<TagPairSimilarity | null>(null);
  const similar = useQuery(queries.similarTagPairs(threshold));

  const pairs = (similar.data ?? []).filter(
    (row): row is TagPairSimilarity => "sim_score" in row,
  );
  const term = search.nome?.toLowerCase();
  const visible = pairs.filter((pair) => {
    if (!term) return true;
    return pair.name_1.toLowerCase().includes(term) || pair.name_2.toLowerCase().includes(term);
  });
  const shown = showAll ? visible : visible.slice(0, 100);

  /**
   * A merge touches four screens at once: the pairs it just changed, the ledger it writes, the
   * clusters a future suggestion may re-propose, and every description that carried either spelling.
   */
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-log"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-xs">
          <span className="text-(--color-muted)">limiar</span>
          <Input
            type="number"
            step="0.05"
            min="0.3"
            max="1"
            className="w-24"
            value={threshold}
            onChange={(event) => patch({ limiar: Number(event.target.value) })}
          />
        </label>
        <Input
          className="max-w-xs"
          placeholder="filtrar por nome…"
          defaultValue={search.nome ?? ""}
          onChange={(event) => patch({ nome: event.target.value || undefined })}
        />
      </div>

      <p className="max-w-3xl text-xs text-(--color-muted)">
        Pares por similaridade de trigrama. É a evidência que a proposta de merge usa — mostrada crua, sem julgar:
        <code> 'alameda cabral' </code> e <code> 'al. alameda cabral' </code> têm similaridade 1.000, e nenhum
        limiar distingue sozinho o que é abreviação do que é outra coisa. Por isso o par traz o botão de unificar e
        a escolha da canônica: a decisão é sua, com o impacto na frente, e o ledger desfaz.
      </p>

      {similar.error ? <ErrorState error={similar.error} /> : null}
      {similar.isPending ? <Spinner /> : null}

      {pending ? (
        <MergePairPanel pair={pending} onMerged={invalidate} onClose={() => setPending(null)} />
      ) : null}

      {similar.data && pairs.length === 0 ? (
        <EmptyState
          title="Nenhum par acima do limiar"
          hint="Baixe o limiar para ver pares mais distantes, ou rode uma proposta de merge para registrar os clusters."
        />
      ) : null}

      {shown.length > 0 ? (
        <Card>
          <CardHeader className="flex items-center justify-between text-xs text-(--color-muted)">
            <span>
              {formatCount(visible.length)} par(es)
              {term ? ` para “${search.nome}”` : ""} de {formatCount(pairs.length)}
            </span>
          </CardHeader>
          <CardBody className="p-0">
            <ul className="divide-y divide-(--color-line) text-sm">
              {shown.map((pair) => (
                <li key={`${pair.id_1}-${pair.id_2}`} className="flex items-center justify-between gap-3 px-3 py-1.5">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate">{pair.name_1}</span>
                    {/*
                      The identifiers are not decoration: two rows can read the same and the panel asks
                      which side is canonical — without the ids the archivist cannot tell them apart.
                    */}
                    <code className="text-[10px] text-(--color-muted)">#{pair.id_1}</code>
                    <span className="text-(--color-muted)">↔</span>
                    <span className="truncate">{pair.name_2}</span>
                    <code className="text-[10px] text-(--color-muted)">#{pair.id_2}</code>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="tabular-nums text-(--color-muted)">{pair.sim_score.toFixed(3)}</span>
                    <Button size="sm" variant="secondary" onClick={() => setPending(pair)}>
                      unificar ↦
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {!showAll && visible.length > shown.length ? (
        <div>
          <Button size="sm" onClick={() => setShowAll(true)}>
            mostrar os {formatCount(visible.length)} pares
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The confirmation step of a hand-picked merge, and the only place the effect is stated.
 *
 * The dry run is fetched as the panel opens and the button waits for it: the numbers the archivist
 * approves come from the same planner the write executes, and ``category_would_be_lost`` is the one
 * warning that has to be read **before** the click — approving on the hope that the pair is harmless
 * is exactly what the measurement forbade (``rua 24 de maio`` <- ``rua 13 de maio``).
 *
 * Unlike the entity merge, this one is reversible: the ledger keeps the tag, its links, its
 * classification and the spellings earlier merges absorbed, and the Propostas tab restores them.
 */
function MergePairPanel({
  pair,
  onMerged,
  onClose,
}: {
  pair: TagPairSimilarity;
  onMerged: () => void;
  onClose: () => void;
}) {
  const [canonicalId, setCanonicalId] = useState(pair.id_1);
  const [outcome, setOutcome] = useState<MergeResponse | null>(null);

  /**
   * The impact carries only the drawer **id**, and a number is not a decision anybody can read.
   *
   * The catalogue is already cached by the categories screen, so naming the drawer costs no request
   * the archivist would not have paid anyway.
   */
  const categories = useQuery(queries.macroCategories());

  const absorbedId = canonicalId === pair.id_1 ? pair.id_2 : pair.id_1;
  const nameOf = (tagId: number) => (tagId === pair.id_1 ? pair.name_1 : pair.name_2);
  const categoryName = (categoryId: number) =>
    categories.data?.find((category) => category.category_id === categoryId)?.name ?? `#${categoryId}`;

  const preview = useQuery({
    // Deliberately **not** under ``["taxonomy", "tags"]``: the merge invalidates that prefix, and a
    // preview keyed inside it would refetch itself with the pair it just absorbed — turning a
    // successful merge into a red panel.
    queryKey: ["taxonomy", "merge-preview", canonicalId, absorbedId],
    queryFn: () => previewTagPair({ canonical_id: canonicalId, ids_to_merge: [absorbedId] }),
    staleTime: 30_000,
  });

  const merge = useMutation({
    mutationFn: () =>
      mergeTags({
        canonical_id: canonicalId,
        ids_to_merge: [absorbedId],
        new_name: null,
        changed_by: null,
      }),
    onSuccess: (data) => {
      setOutcome(data);
      onMerged();
    },
  });

  const tagsDeleted = preview.data?.tags_deleted ?? [];
  // ``category_would_be_lost`` is true only when the canonical has no drawer and a member does, so
  // every drawer listed here is exactly the classification that would disappear.
  const lostDrawers = [
    ...new Set(
      tagsDeleted
        .filter((impact) => impact.macro_category_id !== null)
        .map((impact) => categoryName(impact.macro_category_id as number)),
    ),
  ];

  return (
    <Card className="ring-(--color-accent)/40">
      <CardBody className="grid gap-3">
        <p className="text-sm font-semibold">Unificar duas tags</p>

        <div className="grid gap-2 text-xs">
          {[pair.id_1, pair.id_2].map((tagId) => (
            <label key={tagId} className="flex items-center gap-2">
              <input
                type="radio"
                name={`canonical-tag-${pair.id_1}-${pair.id_2}`}
                checked={canonicalId === tagId}
                disabled={outcome !== null}
                onChange={() => {
                  setCanonicalId(tagId);
                  setOutcome(null);
                }}
              />
              <span className={canonicalId === tagId ? "font-medium" : "text-(--color-muted)"}>
                {nameOf(tagId)} <code className="text-[10px]">#{tagId}</code>
                {canonicalId === tagId ? " — mantida (canônica)" : " — absorvida"}
              </span>
            </label>
          ))}
        </div>

        <p className="text-xs text-(--color-muted)">
          A similaridade não diz qual das duas é a boa: o par vem cru. Trocar a canônica recalcula o impacto com o
          mesmo planejador do unificar.
        </p>

        {preview.isPending ? <Spinner label="Conferindo o impacto…" /> : null}
        {preview.error ? <ErrorState error={preview.error} /> : null}

        {preview.data ? (
          <div className="grid gap-1 rounded-md bg-black/[0.02] p-3 text-xs ring-1 ring-(--color-line)">
            <p className="font-medium">Nada foi escrito ainda. O unificar usa este mesmo planejador.</p>
            <p className="text-(--color-muted)">
              {formatCount(preview.data.documents_updated)} documento(s) atualizado(s) ·{" "}
              {formatCount(preview.data.links_rewritten)} vínculo(s) reescrito(s) ·{" "}
              {formatCount(tagsDeleted.length)} tag(s) absorvida(s)
            </p>
            <ul className="text-(--color-muted)">
              {tagsDeleted.map((impact) => (
                <li key={impact.tag_id}>
                  {impact.name} <code className="text-[10px]">#{impact.tag_id}</code> (
                  {formatCount(impact.document_count)} doc
                  {impact.macro_category_id ? `, gaveta ${categoryName(impact.macro_category_id)}` : ""})
                </li>
              ))}
            </ul>
            {(preview.data.synonyms_created ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                grafias registradas: <code>{(preview.data.synonyms_created ?? []).join(", ")}</code>
              </p>
            ) : null}
            {(preview.data.synonyms_repointed ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                grafias reapontadas: <code>{(preview.data.synonyms_repointed ?? []).join(", ")}</code>
              </p>
            ) : null}
            {preview.data.category_would_be_lost ? (
              <p className="rounded bg-(--color-danger)/5 px-2 py-1 text-(--color-danger) ring-1 ring-(--color-danger)/20">
                Esta unificação <strong>apaga uma classificação de assunto</strong>: a tag absorvida está na gaveta{" "}
                <strong>{lostDrawers.join(", ") || "—"}</strong> e a canônica não tem gaveta.
              </p>
            ) : null}
          </div>
        ) : null}

        <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/20">
          Diferente do merge de entidades, este <strong>tem desfazer</strong>: o ledger da aba Propostas guarda a tag,
          os vínculos, a classificação e as grafias, e restaura tudo.
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={!preview.data || merge.isPending || outcome !== null}
            title={preview.data ? undefined : "O impacto é obrigatório: o unificar espera o dry-run."}
            onClick={() => merge.mutate()}
          >
            {merge.isPending ? "Unificando…" : `Unificar ${nameOf(absorbedId)} em ${nameOf(canonicalId)}`}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            {outcome ? "fechar" : "cancelar"}
          </Button>
        </div>

        {merge.error ? <ErrorState error={merge.error} /> : null}

        {outcome ? (
          <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/25">
            {formatCount(outcome.documents_updated)} documento(s) atualizado(s) ·{" "}
            {formatCount(outcome.tags_deleted)} tag(s) absorvida(s). Ledger{" "}
            <code>{(outcome.merge_ids ?? []).join(", ") || "—"}</code>: o desfazer fica na aba Propostas.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

// =============================================================================================
// Propostas de merge
// =============================================================================================

function ProposalsTab({
  search,
  patch,
}: {
  search: TagsSearch;
  patch: (changes: Partial<TagsSearch>) => void;
}) {
  const queryClient = useQueryClient();
  const [threshold, setThreshold] = useState(0.65);
  const [selected, setSelected] = useState<number[]>([]);
  const [batch, setBatch] = useState<BatchMergeResponse | null>(null);
  const [logLimit, setLogLimit] = useState(MERGE_LOG_PAGE_SIZE);

  /**
   * The filters are translated explicitly into the API's own names.
   *
   * Passing the search object straight through looked equivalent and was not: the route's keys are
   * ``motivo``/``min``/``flag`` while the request expects ``reason``/``min_documents``/``flagged_only``,
   * so three of the four controls answered "every cluster" no matter what the archivist chose. A
   * mismatch the type checker cannot see, because the query builder receives an object either way.
   */
  const proposals = useQuery(
    queries.mergeProposals({
      status: search.status,
      reason: search.motivo,
      min_documents: search.min,
      flagged_only: search.flag,
      offset: search.offset,
    }),
  );
  const log = useQuery(queries.mergeLog(logLimit));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-log"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const suggest = useMutation({
    mutationFn: () => suggestMergeProposals({ threshold, limit: 500 }),
    onSuccess: invalidate,
  });

  const apply = useMutation({
    mutationFn: () => applyMergeBatch({ proposal_ids: selected, changed_by: null, note: null }),
    onSuccess: (data) => {
      setBatch(data);
      setSelected([]);
      invalidate();
    },
  });

  /**
   * Brings every approved cluster into the selection, across pages.
   *
   * Without it the archivist with 92 approved clusters would have to page through five screens and
   * tick a box in each. The selection is what the batch sends, so this only fills it — the write is
   * still the explicit "Aplicar em lote" below.
   */
  /**
   * Files away the clusters that have nothing left to absorb.
   *
   * Rejecting is the only verdict the catalogue has for "this is not work any more", and the note
   * records why — the alternative is a queue that keeps offering an apply which cannot succeed.
   */
  const decideMany = useMutation({
    mutationFn: async (proposalIds: number[]) => {
      for (const proposalId of proposalIds) {
        await decideMergeProposal(proposalId, {
          status: "REJECTED",
          decided_by: null,
          note: "Arquivada: os membros já não existem no acervo.",
        });
      }
    },
    onSuccess: invalidate,
  });

  const selectAllApproved = useMutation({
    mutationFn: () => fetchMergeProposals({ status: "APPROVED", limit: MAX_BATCH }),
    onSuccess: (data) =>
      setSelected((current) => [
        ...new Set([...current, ...(data.items ?? []).map((proposal) => proposal.proposal_id)]),
      ]),
  });

  const undo = useMutation({
    mutationFn: (mergeId: number) => undoMerge(mergeId),
    onSuccess: invalidate,
  });

  const items = proposals.data?.items ?? [];
  const total = proposals.data?.total ?? 0;
  const offset = search.offset ?? 0;
  // Approved and waiting for the write. "Aprovar" records the intent; only the apply absorbs, and
  // the ledger below stays put until it runs — which is exactly what looked like a stuck screen.
  const approvedHere = items.filter((proposal) => proposal.status === "APPROVED" && proposal.applicable);
  const approvedNotSelected = approvedHere.filter((proposal) => !selected.includes(proposal.proposal_id));
  // Approved but with nothing left to absorb: the members are gone, so the apply can only fail.
  const fulfilled = items.filter((proposal) => proposal.status === "APPROVED" && !proposal.applicable);

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
          {suggest.isPending ? "Propondo…" : "Propor clusters"}
        </Button>
        <label className="flex items-center gap-2 text-xs">
          <span className="text-(--color-muted)">limiar</span>
          <Input
            type="number"
            step="0.05"
            min="0.3"
            max="1"
            className="w-24"
            value={threshold}
            onChange={(event) => setThreshold(Number(event.target.value))}
          />
        </label>
        <Select
          className="w-40"
          value={search.status ?? ""}
          onChange={(event) => patch({ status: (event.target.value || undefined) as ProposalStatus | undefined })}
        >
          <option value="">Todos os status</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {labelOf(PROPOSAL_STATUS_LABEL, status)}
            </option>
          ))}
        </Select>
        <Select
          className="w-44"
          value={search.motivo ?? ""}
          onChange={(event) => patch({ motivo: asEnum(event.target.value, REASONS) })}
        >
          <option value="">Todo motivo</option>
          {REASONS.map((reason) => (
            <option key={reason} value={reason}>
              {labelOf(MERGE_REASON_LABEL, reason)}
            </option>
          ))}
        </Select>
        <Input
          type="number"
          className="w-32"
          placeholder="mín. docs"
          defaultValue={search.min ?? ""}
          onChange={(event) => patch({ min: event.target.value ? Number(event.target.value) : undefined })}
        />
        <Button
          size="sm"
          variant={search.flag ? "primary" : "secondary"}
          onClick={() => patch({ flag: search.flag ? undefined : true })}
        >
          só com avisos
        </Button>
      </div>

      {suggest.data ? (
        <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/25">
          Proposta: {formatCount(suggest.data.clusters_found)} cluster(s) encontrados, {formatCount(suggest.data.persisted)}{" "}
          registrados, {formatCount(suggest.data.pending)} pendentes, {formatCount(suggest.data.flagged)} com aviso. Uma
          decisão já tomada não é sobrescrita.
        </p>
      ) : null}
      {suggest.error ? <ErrorState error={suggest.error} /> : null}

      {approvedNotSelected.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md bg-(--color-warn)/5 px-3 py-2 ring-1 ring-(--color-warn)/25">
          <span className="text-xs text-(--color-warn)">
            <strong>{formatCount(approvedNotSelected.length)}</strong> cluster(s) aprovado(s) nesta página{" "}
            <strong>ainda não foram unificados</strong>: aprovar registra a intenção, e só o apply absorve as tags.
            Enquanto ele não roda, o ledger abaixo não muda.
          </span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setSelected((current) => [...new Set([...current, ...approvedNotSelected.map((p) => p.proposal_id)])])}
          >
            incluir as aprovadas desta página
          </Button>
          <Button size="sm" disabled={selectAllApproved.isPending} onClick={() => selectAllApproved.mutate()}>
            {selectAllApproved.isPending ? "Buscando…" : "selecionar todas as aprovadas"}
          </Button>
        </div>
      ) : null}

      {fulfilled.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md bg-(--color-surface-2) px-3 py-2 ring-1 ring-(--color-line)">
          <span className="text-xs text-(--color-muted)">
            <strong>{formatCount(fulfilled.length)}</strong> cluster(s) aprovado(s) nesta página{" "}
            <strong>já não têm o que absorver</strong>: os membros foram unificados por outra mesclagem (ou apagados por
            uma purga). Não são falhas — não há nada a aplicar.
          </span>
          <Button
            size="sm"
            variant="ghost"
            disabled={decideMany.isPending}
            onClick={() => decideMany.mutate(fulfilled.map((proposal) => proposal.proposal_id))}
          >
            arquivar as já cumpridas
          </Button>
        </div>
      ) : null}

      {selected.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-(--color-accent)/5 px-3 py-2 ring-1 ring-(--color-accent)/25">
          <span className="text-xs">
            {formatCount(selected.length)} cluster(s) selecionado(s) para aplicar
          </span>
          <Button
            size="sm"
            variant="primary"
            disabled={apply.isPending || selected.length > MAX_BATCH}
            title={selected.length > MAX_BATCH ? `O lote aceita no máximo ${MAX_BATCH} clusters.` : undefined}
            onClick={() => apply.mutate()}
          >
            {apply.isPending ? "Aplicando…" : "Aplicar em lote"}
          </Button>
          {selected.length > MAX_BATCH ? (
            <span className="text-xs text-(--color-danger)">
              {formatCount(selected.length)} selecionados: o lote aceita no máximo {MAX_BATCH}. Aplique em partes.
            </span>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            limpar seleção
          </Button>
        </div>
      ) : null}

      {apply.error ? <ErrorState error={apply.error} /> : null}
      {batch ? (
        <div className="grid gap-1 rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs ring-1 ring-(--color-ok)/25">
          <p className="font-medium text-(--color-ok)">
            {formatCount((batch.applied ?? []).length)} cluster(s) aplicado(s)
            {(batch.skipped ?? []).length > 0
              ? `, ${formatCount((batch.skipped ?? []).length)} já aplicado(s) antes (ignorados)`
              : ""}
            {", "}
            {formatCount((batch.failed ?? []).length)} falha(s).
          </p>
          {(batch.applied ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-muted)">
              #{entry.proposal_id}: {formatCount(entry.documents_updated)} documento(s), {formatCount(entry.tags_deleted)}{" "}
              tag(s) absorvida(s) · ledger {(entry.merge_ids ?? []).join(", ")}
            </p>
          ))}
          {(batch.skipped ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-muted)">
              #{entry.proposal_id} ignorado: {entry.error}
            </p>
          ))}
          {(batch.failed ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-danger)">
              #{entry.proposal_id} não aplicado: {entry.error}
            </p>
          ))}
        </div>
      ) : null}

      {proposals.error ? <ErrorState error={proposals.error} /> : null}
      {proposals.isPending ? (
        <div className="grid gap-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-32" />
          ))}
        </div>
      ) : null}

      {proposals.data && total === 0 ? (
        <EmptyState
          title="Nenhuma proposta com este filtro"
          hint="Rode 'Propor clusters' para registrar os pares acima do limiar. A proposta não unifica nada: ela só escreve a pergunta."
          action={
            <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
              Propor clusters
            </Button>
          }
        />
      ) : null}

      <ul className="grid gap-2">
        {items.map((proposal) => (
          <li key={proposal.proposal_id}>
            <ProposalCard
              proposal={proposal}
              selected={selected.includes(proposal.proposal_id)}
              onToggle={(checked) =>
                setSelected((current) =>
                  checked ? [...current, proposal.proposal_id] : current.filter((id) => id !== proposal.proposal_id),
                )
              }
              // Approving selects it for the batch, so the step that actually writes is one click
              // away instead of hidden behind a checkbox the archivist has to find.
              onApproved={() =>
                setSelected((current) =>
                  current.includes(proposal.proposal_id) ? current : [...current, proposal.proposal_id],
                )
              }
            />
          </li>
        ))}
      </ul>

      {total > PROPOSALS_PAGE_SIZE ? (
        <div className="flex items-center justify-between text-sm">
          <Button
            size="sm"
            disabled={offset === 0}
            onClick={() => patch({ offset: Math.max(0, offset - PROPOSALS_PAGE_SIZE) })}
          >
            ← Anterior
          </Button>
          <span className="text-xs text-(--color-muted)">
            {formatCount(offset + 1)}–{formatCount(Math.min(offset + PROPOSALS_PAGE_SIZE, total))} de {formatCount(total)}
          </span>
          <Button
            size="sm"
            disabled={offset + PROPOSALS_PAGE_SIZE >= total}
            onClick={() => patch({ offset: offset + PROPOSALS_PAGE_SIZE })}
          >
            Próxima →
          </Button>
        </div>
      ) : null}

      <Card>
        <CardHeader className="text-sm font-semibold">Ledger dos merges</CardHeader>
        <CardBody className="grid gap-2">
          <p className="text-xs text-(--color-muted)">
            Aqui só entram merges <strong>aplicados</strong>: aprovar não escreve nesta lista. Cada linha guarda o
            estado anterior — tag, vínculos, classificação e grafias — e o desfazer restaura tudo.
          </p>
          {log.isPending ? <Spinner label="Lendo o ledger…" /> : null}
          {log.error ? <ErrorState error={log.error} /> : null}
          {log.data && (log.data.items ?? []).length === 0 ? (
            <EmptyState title="Nenhum merge aplicado ainda" hint="O ledger registra cada tag absorvida, com o antes." />
          ) : null}
          <ul className="divide-y divide-(--color-line) text-xs">
            {(log.data?.items ?? []).map((entry) => (
              <li key={entry.merge_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="min-w-0">
                  <span className="font-medium">{entry.absorbed_name}</span>
                  <span className="text-(--color-muted)"> → {entry.canonical_name}</span>
                  <span className="text-(--color-muted)">
                    {" "}
                    · {formatCount(entry.document_count)} doc(s) · {formatDateTime(entry.changed_at)}
                    {entry.changed_by ? ` · por ${entry.changed_by}` : ""}
                  </span>
                </span>
                {entry.undone_at ? (
                  <Badge tone="neutral">desfeito em {formatDateTime(entry.undone_at)}</Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={undo.isPending}
                    title="Restaura a tag, os vínculos, a classificação e as grafias absorvidas."
                    onClick={() => undo.mutate(entry.merge_id)}
                  >
                    desfazer
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {undo.error ? <ErrorState error={undo.error} /> : null}
          {log.data && log.data.total > logLimit ? (
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" onClick={() => setLogLimit((current) => current + MERGE_LOG_PAGE_SIZE)}>
                ver mais
              </Button>
              <span className="text-xs text-(--color-muted)">
                mostrando os {formatCount(logLimit)} mais recentes de {formatCount(log.data.total)} merge(s) aplicado(s)
              </span>
            </div>
          ) : null}
        </CardBody>
      </Card>

    </div>
  );
}

/**
 * One cluster, with the evidence and the two decisions that are possible about it.
 *
 * The preview is a step, not a decoration: ``category_would_be_lost`` is the only warning that the
 * merge would destroy a classification, and it has to be seen **before** the verdict, because
 * approving records an intent that the next suggestion run will not overwrite.
 */
function ProposalCard({
  proposal,
  selected,
  onToggle,
  onApproved,
}: {
  proposal: TagMergeProposal;
  selected: boolean;
  onToggle: (checked: boolean) => void;
  onApproved: () => void;
}) {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<MergePreview | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const decide = useMutation({
    mutationFn: (status: "APPROVED" | "REJECTED") =>
      decideMergeProposal(proposal.proposal_id, { status, decided_by: null, note: null }),
    onSuccess: (_data, status) => {
      invalidate();
      if (status === "APPROVED") onApproved();
    },
  });

  const dryRun = useMutation({
    mutationFn: () => previewMerge(proposal.proposal_id),
    onSuccess: setPreview,
  });

  const flags = proposal.review_flags ?? [];

  return (
    <Card>
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <Badge tone={PROPOSAL_STATUS_TONE[proposal.status] ?? "neutral"}>
              {labelOf(PROPOSAL_STATUS_LABEL, proposal.status)}
            </Badge>
            <span className="text-sm font-medium">{proposal.canonical_name}</span>
            <Badge tone={MERGE_REASON_TONE[proposal.reason] ?? "neutral"}>
              {labelOf(MERGE_REASON_LABEL, proposal.reason)}
            </Badge>
            <span className="text-xs text-(--color-muted)">{formatCount(proposal.total_documents)} documento(s)</span>
          </span>
          {proposal.status === "APPROVED" && proposal.applicable ? (
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={selected} onChange={(event) => onToggle(event.target.checked)} />
              incluir no lote de apply
            </label>
          ) : null}
          {proposal.status === "APPROVED" && !proposal.applicable ? (
            <span className="text-xs text-(--color-muted)" title="Os membros já não existem no acervo.">
              sem membros para absorver
            </span>
          ) : null}
        </div>

        {flags.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {flags.map((flag) => (
              <li key={flag}>
                <Badge tone="warn" title={REVIEW_FLAG_HINT[flag]}>
                  {labelOf(REVIEW_FLAG_LABEL, flag)}
                </Badge>
              </li>
            ))}
          </ul>
        ) : null}

        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {(proposal.members ?? []).map((member) => (
            <li key={member.tag_id} className={member.tag_id === proposal.canonical_id ? "font-medium" : ""}>
              {member.name}
              <span className="text-(--color-muted)"> ({formatCount(member.document_count)})</span>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={dryRun.isPending} onClick={() => dryRun.mutate()}>
            {dryRun.isPending ? "Conferindo…" : "Conferir impacto"}
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={decide.isPending || proposal.status === "APPROVED"}
            onClick={() => decide.mutate("APPROVED")}
          >
            Aprovar
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={decide.isPending || proposal.status === "REJECTED"}
            onClick={() => decide.mutate("REJECTED")}
          >
            Rejeitar
          </Button>
          {proposal.decided_by || proposal.decision_note ? (
            <span className="text-xs text-(--color-muted)">
              {proposal.decided_by ? `por ${proposal.decided_by}` : ""}
              {proposal.decision_note ? ` · ${proposal.decision_note}` : ""}
            </span>
          ) : null}
        </div>

        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
        {decide.error ? <ErrorState error={decide.error} /> : null}

        {preview ? (
          <div className="grid gap-1 rounded-md bg-black/[0.02] p-3 text-xs ring-1 ring-(--color-line)">
            <p className="font-medium">Nada foi escrito ainda. O apply usa este mesmo planejador.</p>
            <p className="text-(--color-muted)">
              {formatCount(preview.documents_updated)} documento(s) atualizado(s) ·{" "}
              {formatCount(preview.links_rewritten)} vínculo(s) reescrito(s) ·{" "}
              {formatCount((preview.tags_deleted ?? []).length)} tag(s) absorvida(s)
            </p>
            <ul className="text-(--color-muted)">
              {(preview.tags_deleted ?? []).map((impact) => (
                <li key={impact.tag_id}>
                  {impact.name} ({formatCount(impact.document_count)} doc
                  {impact.macro_category_id ? `, gaveta ${impact.macro_category_id}` : ""})
                </li>
              ))}
            </ul>
            {(preview.synonyms_created ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                grafias registradas: <code>{(preview.synonyms_created ?? []).join(", ")}</code>
              </p>
            ) : null}
            {(preview.synonyms_repointed ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                grafias reapontadas: <code>{(preview.synonyms_repointed ?? []).join(", ")}</code>
              </p>
            ) : null}
            {preview.category_would_be_lost ? (
              <p className="rounded bg-(--color-danger)/5 px-2 py-1 text-(--color-danger) ring-1 ring-(--color-danger)/20">
                Esta unificação <strong>apaga uma classificação de assunto</strong>: um dos membros está numa gaveta que
                a canônica não tem.
              </p>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

// =============================================================================================
// Stopwords — os termos banidos, e a única escrita destrutiva sem undo
// =============================================================================================

/** "pessoas, vista aérea" → ["pessoas", "vista aérea"]. */
function splitWords(text: string): string[] {
  return text
    .split(/[,\n;]/)
    .map((word) => word.trim())
    .filter((word) => word.length > 0);
}

/**
 * The banned terms, and the purge.
 *
 * The screen keeps three things apart that are easy to confuse, and each one is stated where it
 * matters: banning a word **deletes nothing**; the purge deletes the tags with that name and **has
 * no undo** (unlike the merge, which keeps a ledger); and the scope decides which of those is even
 * possible — a term banned from the NER axis never reaches the subject purge.
 */
function StopwordsTab({ search, patch }: { search: TagsSearch; patch: (changes: Partial<TagsSearch>) => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [draftScope, setDraftScope] = useState<StopwordsScope>("TAG");
  const [preview, setPreview] = useState<StopwordPurgePreview | null>(null);
  const [purged, setPurged] = useState<number | null>(null);

  const stopwords = useQuery(queries.stopwords(search.escopo));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "stopwords"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const ban = useMutation({
    mutationFn: () => banStopwords({ words: splitWords(draft), scope: draftScope }),
    onSuccess: () => {
      setDraft("");
      invalidate();
    },
  });

  const unban = useMutation({
    mutationFn: (word: string) => unbanStopwords({ words: [word] }),
    onSuccess: invalidate,
  });

  const dryRun = useMutation({
    mutationFn: previewStopwordPurge,
    onSuccess: (data) => {
      setPreview(data);
      setPurged(null);
    },
  });

  const purge = useMutation({
    mutationFn: purgeStopwords,
    onSuccess: (data) => {
      setPurged(data.tags_deleted);
      setPreview(null);
      invalidate();
    },
  });

  const words = stopwords.data ?? [];
  const byScope = (scope: StopwordsScope) => words.filter((item) => item.scope === scope);

  return (
    <div className="grid gap-4">
      <p className="max-w-3xl rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
        <strong>Banir não apaga nada.</strong> Banir registra que o termo não vale; a <strong>purga</strong> é o passo
        que apaga as tags com esse nome — e ela <strong>não tem undo</strong>: o merge guarda o estado anterior e
        restaura, a purga não. Por isso ela vem sempre depois de conferir o impacto.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={search.escopo ? "secondary" : "primary"} onClick={() => patch({ escopo: undefined })}>
          Todos os eixos ({formatCount(words.length)})
        </Button>
        {SCOPE_VALUES.map((scope) => (
          <Button
            key={scope}
            size="sm"
            variant={search.escopo === scope ? "primary" : "secondary"}
            title={STOPWORD_SCOPE_HINT[scope]}
            onClick={() => patch({ escopo: scope })}
          >
            {labelOf(STOPWORD_SCOPE_LABEL, scope)} ({formatCount(byScope(scope).length)})
          </Button>
        ))}
      </div>

      {stopwords.error ? <ErrorState error={stopwords.error} /> : null}
      {stopwords.isPending ? <Spinner label="Lendo os termos banidos…" /> : null}

      {stopwords.data && words.length === 0 ? (
        <EmptyState
          title="Nenhum termo banido"
          hint="Banir um termo o tira do eixo escolhido. Nada é apagado por banir: a purga é um passo separado, abaixo."
        />
      ) : null}

      {words.length > 0 ? (
        <Card>
          <CardHeader className="text-sm font-semibold">Termos banidos</CardHeader>
          <CardBody className="p-0">
            <ul className="divide-y divide-(--color-line) text-sm">
              {words.map((item) => (
                <li key={item.word} className="flex items-center justify-between gap-3 px-3 py-1.5">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate">{item.word}</span>
                    <Badge tone={item.scope === "ENTITY" ? "neutral" : "accent"} title={STOPWORD_SCOPE_HINT[item.scope]}>
                      {labelOf(STOPWORD_SCOPE_LABEL, item.scope)}
                    </Badge>
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={unban.isPending}
                    onClick={() => unban.mutate(item.word)}
                  >
                    desbanir
                  </Button>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="text-sm font-semibold">Banir termos</CardHeader>
        <CardBody className="grid gap-2">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex-1">
              <span className="mb-1 block text-xs font-medium text-(--color-muted)">
                Termos, separados por vírgula ou linha
              </span>
              <Input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="ex.: pessoas, vista aérea"
                onKeyDown={(event) => {
                  if (event.key === "Enter" && splitWords(draft).length > 0) ban.mutate();
                }}
              />
            </label>
            <label className="w-56">
              <span className="mb-1 block text-xs font-medium text-(--color-muted)">Eixo</span>
              <Select value={draftScope} onChange={(event) => setDraftScope(event.target.value as StopwordsScope)}>
                {SCOPE_VALUES.map((scope) => (
                  <option key={scope} value={scope}>
                    {labelOf(STOPWORD_SCOPE_LABEL, scope)}
                  </option>
                ))}
              </Select>
            </label>
            <Button
              variant="primary"
              disabled={splitWords(draft).length === 0 || ban.isPending}
              onClick={() => ban.mutate()}
            >
              {ban.isPending ? "Banindo…" : "Banir"}
            </Button>
          </div>
          <p className="text-xs text-(--color-muted)">{STOPWORD_SCOPE_HINT[draftScope]}</p>
          {ban.error ? <ErrorState error={ban.error} /> : null}
          {unban.error ? <ErrorState error={unban.error} /> : null}
        </CardBody>
      </Card>

      <Card className="ring-(--color-danger)/30">
        <CardHeader className="text-sm font-semibold text-(--color-danger)">Purgar as tags banidas</CardHeader>
        <CardBody className="grid gap-3">
          <p className="text-xs text-(--color-muted)">
            A purga apaga toda tag cujo nome seja um termo banido nos eixos <code>TAG</code> ou <code>ALL</code>. Os
            vínculos caem junto e a classificação da tag vai embora. <strong>Não há desfazer.</strong>
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={dryRun.isPending || purge.isPending} onClick={() => dryRun.mutate()}>
              {dryRun.isPending ? "Conferindo…" : "Conferir o que seria apagado"}
            </Button>
            <Button
              variant="danger"
              disabled={!preview || preview.total_tags === 0 || purge.isPending}
              title={preview ? undefined : "O impacto é obrigatório: confira o que seria apagado primeiro."}
              onClick={() => purge.mutate()}
            >
              {purge.isPending
                ? "Apagando…"
                : preview
                  ? `Apagar ${formatCount(preview.total_tags)} tag(s)`
                  : "Apagar (confira antes)"}
            </Button>
          </div>

          {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
          {purge.error ? <ErrorState error={purge.error} /> : null}

          {preview ? (
            <div className="grid gap-2 rounded-md bg-(--color-danger)/5 p-3 text-xs ring-1 ring-(--color-danger)/20">
              <p>
                Nada foi apagado ainda. Seriam <strong>{formatCount(preview.total_tags)} tag(s)</strong> em{" "}
                <strong>{formatCount(preview.total_documents)} descrição(ões)</strong>.
              </p>
              {(preview.stopwords ?? []).length > 0 ? (
                <p className="text-(--color-muted)">
                  termos que a purga alcança: <code>{(preview.stopwords ?? []).join(", ")}</code>
                </p>
              ) : null}
              {preview.total_tags === 0 ? (
                <p className="text-(--color-muted)">
                  Nenhuma tag do acervo tem um desses nomes — não há o que apagar.
                </p>
              ) : (
                <ul className="max-h-64 overflow-y-auto">
                  {(preview.tags ?? []).map((tag) => (
                    <li key={tag.tag_id} className="flex items-center justify-between gap-3 py-0.5">
                      <span className="truncate">{tag.name}</span>
                      <span className="shrink-0 tabular-nums text-(--color-muted)">
                        {formatCount(tag.document_count)} doc
                        {tag.macro_category_name ? ` · ${tag.macro_category_name}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          {purged !== null ? (
            <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/25">
              {formatCount(purged)} tag(s) apagada(s). Isto <strong>não</strong> aparece no ledger de merges: não há
              estado anterior guardado para restaurar.
            </p>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

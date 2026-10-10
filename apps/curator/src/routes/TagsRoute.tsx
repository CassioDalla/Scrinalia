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
import { LedgerList } from "@/components/ui/LedgerList";
import { Notice } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { PageBody } from "@/components/layout/PageBody";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDateTime } from "@/lib/format";
import { asBoolean, asEnum, asNumber, asString } from "@/lib/search";
import { useDebounced } from "@/lib/useDebounced";
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

/**
 * What a merge panel needs to know about one tag: the row it points at, and what it reads.
 *
 * Deliberately *not* the contract's ``TagMergeMember``: that one carries ``document_count``, which is
 * the proposal's refreshed evidence and not something a hand-picked pair knows. Requiring it here
 * would force the screen to invent a number to fill a field nothing reads.
 */
type MergeCandidate = { tag_id: number; name: string };

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
      <PageHeader screen="tags" />

      <div className="px-6">
        <Tabs
          items={TABS}
          active={search.aba ?? "relevancia"}
          onChange={(id) => patch({ aba: id })}
        />
      </div>

      <PageBody>
        {search.aba === "similaridade" ? (
          <SimilarityTab search={search} patch={patch} />
        ) : search.aba === "propostas" ? (
          <ProposalsTab search={search} patch={patch} />
        ) : search.aba === "stopwords" ? (
          <StopwordsTab search={search} patch={patch} />
        ) : (
          <RelevanceTab search={search} patch={patch} />
        )}
      </PageBody>
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
  /** One row opened by its own button: the panel renders right under it. */
  const [openPair, setOpenPair] = useState<TagPairSimilarity | null>(null);
  /** Tags marked across rows, for the case the pair list cannot express: one merge out of many rows. */
  const [marked, setMarked] = useState<MergeCandidate[]>([]);
  const [clusterOpen, setClusterOpen] = useState(false);
  const [lastMerge, setLastMerge] = useState<{ label: string; outcome: MergeResponse } | null>(null);

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
   * agrupamentos a future suggestion may re-propose, and every description that carried either spelling.
   */
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-log"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const isMarked = (tagId: number) => marked.some((member) => member.tag_id === tagId);

  /**
   * A row is marked as a whole.
   *
   * The unit the archivist reads is the pair — "these two are the same thing" — so ticking it has to
   * add *both* sides; adding only one would build a agrupamento out of half of what was on screen. Two
   * rows that share a side (`carlos de carvalho` ↔ X and `carlos de carvalho` ↔ Y) therefore merge
   * into three tags, which is exactly the case the pair list cannot express and the reason marking a
   * row exists at all.
   */
  const rowMarked = (pair: TagPairSimilarity) => isMarked(pair.id_1) && isMarked(pair.id_2);

  const toggleRow = (pair: TagPairSimilarity) => {
    const members = [
      { tag_id: pair.id_1, name: pair.name_1 },
      { tag_id: pair.id_2, name: pair.name_2 },
    ];
    setMarked((current) => {
      const already = members.every((member) => current.some((item) => item.tag_id === member.tag_id));
      if (already) return current.filter((item) => !members.some((member) => member.tag_id === item.tag_id));
      return [...current, ...members.filter((member) => !current.some((item) => item.tag_id === member.tag_id))];
    });
  };

  const clearMarked = () => {
    setMarked([]);
    setClusterOpen(false);
  };

  /**
   * A successful merge invalidates the data and **leaves the panel open**.
   *
   * The panel is the only place the write is reported ("N documentos atualizados, M tags absorvidas,
   * ledger 195"), and closing it on success threw that message away: the archivist clicked, the panel
   * vanished and nothing said whether it had worked. Closing is a separate click, and it is also what
   * clears the marks — the absorbed tags no longer exist, so the floating bar would be pointing at
   * names that are gone.
   */
  const afterMerge = (outcome: MergeResponse) => {
    setLastMerge({ label: "Mesclagem aplicada", outcome });
    setMarked([]);
    invalidate();
  };

  const closePanel = () => {
    setOpenPair(null);
    setClusterOpen(false);
    setMarked([]);
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
        limiar distingue sozinho o que é abreviação do que é outra coisa. Por isso o par traz o botão de mesclar e
        a escolha da canônica: a decisão é sua, com o impacto na frente, e o ledger desfaz. Para mesclar mais de um
        par de uma vez — “carlos de carvalho” aparece em várias linhas —, marque as linhas e use a barra que aparece
        embaixo.
      </p>

      {similar.error ? <ErrorState error={similar.error} /> : null}
      {similar.isPending ? <Spinner /> : null}

      {lastMerge ? <MergeOutcome label={lastMerge.label} outcome={lastMerge.outcome} /> : null}

      {/*
        Two rows at once is a different operation from one row, and it gets the panel in the place the
        archivist suggested for it: the top, because there is no single row it belongs under.
      */}
      {clusterOpen && marked.length >= 2 ? (
        <TagMergePanel
          members={marked}
          title={`Mesclar ${formatCount(marked.length)} tags marcadas`}
          hint="Estas tags vieram de linhas diferentes da lista: a canônica é escolhida abaixo, e o impacto é recalculado para o conjunto inteiro."
          onMerged={afterMerge}
          onClose={closePanel}
        />
      ) : null}

      {similar.data && pairs.length === 0 ? (
        <EmptyState
          title="Nenhum par acima do limiar"
          hint="Baixe o limiar para ver pares mais distantes, ou rode uma proposta de merge para registrar os agrupamentos."
        />
      ) : null}

      {shown.length > 0 ? (
        <Card>
          <CardHeader className="flex items-center justify-between text-xs text-(--color-muted)">
            <span>
              {formatCount(visible.length)} par(es)
              {term ? ` para “${search.nome}”` : ""} de {formatCount(pairs.length)}
            </span>
            {marked.length > 0 ? (
              <Button size="sm" variant="ghost" onClick={clearMarked}>
                limpar marcação ({formatCount(marked.length)})
              </Button>
            ) : null}
          </CardHeader>
          <CardBody className="p-0">
            <ul className="divide-y divide-(--color-line) text-sm">
              {shown.map((pair) => (
                <li key={`${pair.id_1}-${pair.id_2}`}>
                  <div className="flex items-center justify-between gap-3 px-3 py-1.5">
                    <span className="flex min-w-0 items-center gap-2">
                      <input
                        type="checkbox"
                        checked={rowMarked(pair)}
                        onChange={() => toggleRow(pair)}
                        title="Marcar as duas tags desta linha para mesclar em conjunto"
                        aria-label={`Marcar ${pair.name_1} e ${pair.name_2}`}
                      />
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
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setOpenPair(openPair === pair ? null : pair)}
                      >
                        {openPair === pair ? ACTION.close.label : "Mesclar ↦"}
                      </Button>
                    </span>
                  </div>
                  {/*
                    The panel opens *under its own row*, which is the whole point: it used to render at
                    the top of the page, so unifying a row from the bottom meant scrolling back up to
                    read the impact and back down to find the next one.
                  */}
                  {openPair === pair ? (
                    <div className="px-3 pb-3">
                      <TagMergePanel
                        members={[
                          { tag_id: pair.id_1, name: pair.name_1 },
                          { tag_id: pair.id_2, name: pair.name_2 },
                        ]}
                        title="Mesclar duas tags"
                        onMerged={afterMerge}
                        onClose={closePanel}
                      />
                    </div>
                  ) : null}
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

      {/* The bar floats over the list so the decision is reachable from anywhere in it. */}
      {marked.length >= 2 && !clusterOpen ? (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-40 flex justify-center">
          <div className="pointer-events-auto flex flex-wrap items-center gap-3 rounded-full bg-(--color-ink) px-4 py-2 text-sm text-white shadow-lg">
            <span>
              {formatCount(marked.length)} tags marcadas em {formatCount(countRows(marked, pairs))} linha(s)
            </span>
            <Button size="sm" variant="primary" onClick={() => setClusterOpen(true)}>
              Mesclar tags
            </Button>
            <button className="text-xs text-white/70 hover:text-white" onClick={clearMarked}>
              limpar
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The report of a merge, rendered by the **screen** and not by the row that started it.
 *
 * A merge is a write over the vocabulary, so the pair or the agrupamento that triggered it usually stops
 * existing in the very refetch that follows: the row disappears and any message living inside it
 * disappears with it. The archivist clicked, the panel vanished and nothing said whether it had
 * worked — which is the one thing a destructive-looking operation must never do.
 */
function MergeOutcome({ label, outcome }: { label: string; outcome: MergeResponse }) {
  return (
    <Notice tone="ok">
      <strong>{label}</strong> · {formatCount(outcome.documents_updated)} documento(s) atualizado(s) ·{" "}
      {formatCount(outcome.tags_deleted)} tag(s) absorvida(s) · ledger{" "}
      <code>{(outcome.merge_ids ?? []).join(", ") || "—"}</code>. O desfazer está no ledger de merges.
    </Notice>
  );
}

/** How many of the marked tags came from the rows on screen — the bar's own honesty check. */
function countRows(marked: MergeCandidate[], pairs: TagPairSimilarity[]): number {
  const ids = new Set(marked.map((member) => member.tag_id));
  return pairs.filter((pair) => ids.has(pair.id_1) || ids.has(pair.id_2)).length;
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
function TagMergePanel({
  members,
  title,
  hint,
  initialCanonicalId,
  onMerged,
  onClose,
}: {
  /** Two or more tags. The first is the default canonical, so the order the archivist chose survives. */
  members: MergeCandidate[];
  title?: string;
  hint?: string;
  initialCanonicalId?: number;
  /** Runs after a successful write: the caller invalidates, and the proposal editor closes the row. */
  onMerged: (outcome: MergeResponse) => void;
  onClose: () => void;
}) {
  const first = members[0];
  const [canonicalId, setCanonicalId] = useState(initialCanonicalId ?? first?.tag_id ?? 0);
  /**
   * Members the archivist took out of the agrupamento.
   *
   * This is the whole point of editing a proposal: a machine agrupamento is usually *nearly* right — the
   * report is explicit about it ("289 anos é diferente de 294") — and without a way to drop one tag the
   * only options were to accept a wrong merge or reject a good one. Leaving a member out is also how
   * the pair panel says "actually, only this one".
   */
  const [excluded, setExcluded] = useState<number[]>([]);
  const [outcome, setOutcome] = useState<MergeResponse | null>(null);

  const included = members.filter((member) => !excluded.includes(member.tag_id));
  const absorbed = included.filter((member) => member.tag_id !== canonicalId);

  /**
   * The impact carries only the drawer **id**, and a number is not a decision anybody can read.
   *
   * The catalogue is already cached by the categories screen, so naming the drawer costs no request
   * the archivist would not have paid anyway.
   */
  const categories = useQuery(queries.macroCategories());

  const absorbedIds = absorbed.map((member) => member.tag_id);
  const nameOf = (tagId: number) => members.find((member) => member.tag_id === tagId)?.name ?? `#${tagId}`;
  const categoryName = (categoryId: number) =>
    categories.data?.find((category) => category.category_id === categoryId)?.name ?? `#${categoryId}`;

  const preview = useQuery({
    // Deliberately **not** under ``["taxonomy", "tags"]``: the merge invalidates that prefix, and a
    // preview keyed inside it would refetch itself with the tags it just absorbed — turning a
    // successful merge into a red panel. The key carries the *kept* set, so unchecking a tag
    // recomputes the impact instead of showing the previous agrupamento's numbers.
    queryKey: ["taxonomy", "merge-preview", canonicalId, included.map((m) => m.tag_id).join(",")],
    queryFn: () => previewTagPair({ canonical_id: canonicalId, ids_to_merge: absorbedIds }),
    staleTime: 30_000,
    // A agrupamento with nothing to absorb has no impact to compute, and the write is refused below.
    enabled: absorbedIds.length > 0,
  });

  const merge = useMutation({
    mutationFn: () =>
      mergeTags({
        canonical_id: canonicalId,
        ids_to_merge: absorbedIds,
        new_name: null,
      }),
    onSuccess: (data) => {
      setOutcome(data);
      onMerged(data);
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

  const toggleMember = (tagId: number) => {
    setOutcome(null);
    setExcluded((current) => {
      const next = current.includes(tagId)
        ? current.filter((id) => id !== tagId)
        : [...current, tagId];
      // The canonical cannot be a member that just left: the radio follows the first one still in.
      if (next.includes(canonicalId)) {
        const fallback = members.find((member) => !next.includes(member.tag_id));
        if (fallback) setCanonicalId(fallback.tag_id);
      }
      return next;
    });
  };

  return (
    <Card className="ring-(--color-accent)/40">
      <CardBody className="grid gap-3">
        <p className="text-sm font-semibold">{title ?? "Mesclar tags"}</p>
        {hint ? <p className="text-xs text-(--color-muted)">{hint}</p> : null}

        <div className="grid gap-2 text-xs">
          {members.map((member) => {
            const isCanonical = canonicalId === member.tag_id;
            const out = excluded.includes(member.tag_id);
            return (
              <div
                key={member.tag_id}
                className={
                  "flex flex-wrap items-center gap-2 rounded px-1 py-0.5 " +
                  (out ? "opacity-50" : "")
                }
              >
                <input
                  type="checkbox"
                  checked={!out}
                  disabled={outcome !== null}
                  onChange={() => toggleMember(member.tag_id)}
                  title={out ? "Trazer de volta para o agrupamento" : "Tirar do agrupamento"}
                  aria-label={`Incluir ${member.name} no agrupamento`}
                />
                <input
                  type="radio"
                  name={`canonical-tag-${members.map((item) => item.tag_id).join("-")}`}
                  checked={isCanonical}
                  disabled={out || outcome !== null}
                  onChange={() => {
                    setCanonicalId(member.tag_id);
                    setOutcome(null);
                  }}
                  title="Manter esta grafia"
                />
                <span className={isCanonical ? "font-medium" : "text-(--color-muted)"}>
                  {member.name} <code className="text-[10px]">#{member.tag_id}</code>
                  {out
                    ? " — fora do agrupamento"
                    : isCanonical
                      ? " — mantida (canônica)"
                      : " — absorvida"}
                </span>
              </div>
            );
          })}
        </div>

        <p className="text-xs text-(--color-muted)">
          A similaridade não diz qual delas é a boa: a lista vem crua. Desmarque o que não pertence ao conjunto —
          “289 anos” não é “294 anos” — e o impacto é recalculado com o mesmo planejador da mesclagem.
        </p>

        {preview.isPending ? <Spinner label="Conferindo o impacto…" /> : null}
        {preview.error ? <ErrorState error={preview.error} /> : null}

        {preview.data ? (
          <div className="grid gap-1 rounded-md bg-black/[0.02] p-3 text-xs ring-1 ring-(--color-line)">
            <p className="font-medium">Nada foi escrito ainda. A mesclagem usa este mesmo planejador.</p>
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
                  {impact.macro_category_id ? `, categoria ${categoryName(impact.macro_category_id)}` : ""})
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
              <Notice tone="danger">
                Esta mesclagem <strong>exclui uma classificação de assunto</strong>: a tag absorvida está na categoria{" "}
                <strong>{lostDrawers.join(", ") || "—"}</strong> e a canônica não tem categoria.
              </Notice>
            ) : null}
          </div>
        ) : null}

        <Notice tone="ok">
          Diferente do merge de entidades, este <strong>tem desfazer</strong>: o ledger da aba Propostas guarda a tag,
          os vínculos, a classificação e as grafias, e restaura tudo.
        </Notice>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={!preview.data || merge.isPending || outcome !== null || included.length < 2}
            title={
              included.length < 2
                ? "Um agrupamento precisa de ao menos duas tags: uma canônica e uma absorvida."
                : preview.data
                  ? undefined
                  : "O impacto é obrigatório: conferir o impacto vem antes de mesclar."
            }
            onClick={() => merge.mutate()}
          >
            {merge.isPending
              ? ACTION.merge.pending
              : absorbed.length === 1
                ? `Mesclar ${absorbed[0]?.name} em ${nameOf(canonicalId)}`
                : `Mesclar ${formatCount(absorbed.length)} tags em ${nameOf(canonicalId)}`}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            {outcome ? ACTION.close.label : ACTION.cancel.label}
          </Button>
        </div>

        {merge.error ? <ErrorState error={merge.error} /> : null}

        {outcome ? (
          <Notice tone="ok">
            {formatCount(outcome.documents_updated)} documento(s) atualizado(s) ·{" "}
            {formatCount(outcome.tags_deleted)} tag(s) absorvida(s). Ledger{" "}
            <code>{(outcome.merge_ids ?? []).join(", ") || "—"}</code>: o desfazer fica na aba Propostas.
          </Notice>
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
  const [logTerm, setLogTerm] = useState("");
  /** The agrupamento the archivist is editing before applying — "tira o '289 anos' do meio". */
  const [editing, setEditing] = useState<TagMergeProposal | null>(null);
  const [lastEdited, setLastEdited] = useState<{ proposalId: number; outcome: MergeResponse } | null>(null);

  /**
   * The filters are translated explicitly into the API's own names.
   *
   * Passing the search object straight through looked equivalent and was not: the route's keys are
   * ``motivo``/``min``/``flag`` while the request expects ``reason``/``min_documents``/``flagged_only``,
   * so three of the four controls answered "every agrupamento" no matter what the archivist chose. A
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
  const settledLogTerm = useDebounced(logTerm);
  const log = useQuery(queries.mergeLog(logLimit, settledLogTerm.trim() || undefined));

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
    mutationFn: () => applyMergeBatch({ proposal_ids: selected, note: null }),
    onSuccess: (data) => {
      setBatch(data);
      setSelected([]);
      invalidate();
    },
  });

  /**
   * Brings every approved agrupamento into the selection, across pages.
   *
   * Without it the archivist with 92 approved agrupamentos would have to page through five screens and
   * tick a box in each. The selection is what the batch sends, so this only fills it — the write is
   * still the explicit "Aplicar em lote" below.
   */
  /**
   * Files away the agrupamentos that have nothing left to absorb.
   *
   * Rejecting is the only verdict the catalogue has for "this is not work any more", and the note
   * records why — the alternative is a queue that keeps offering an apply which cannot succeed.
   */
  const decideMany = useMutation({
    mutationFn: async (proposalIds: number[]) => {
      for (const proposalId of proposalIds) {
        await decideMergeProposal(proposalId, {
          status: "REJECTED",
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

  /**
   * Files away the machine's agrupamento after the archivist applied their own version of it.
   *
   * Rejecting is the only verdict the catalogue has for "this question is answered", and it is what
   * keeps the agrupamento from coming back: the suggestion run re-proposes a fingerprint whose row is
   * still ``SUGGESTED``, and a row that left ``SUGGESTED`` is never rewritten. Editing the members in
   * place was the alternative and it does not work — the fingerprint *is* the member list, so the next
   * run would insert the original agrupamento again as brand-new work.
   */
  const closeEdited = useMutation({
    mutationFn: (proposal: TagMergeProposal) =>
      decideMergeProposal(proposal.proposal_id, {
        status: "REJECTED",
        note: `Editada e aplicada à mão: a máquina propôs ${formatCount((proposal.members ?? []).length)} membros e a seleção revisada foi mesclada pelo ledger.`,
      }),
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
          {suggest.isPending ? "Propondo…" : "Propor Agrupamentos"}
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
        <Notice tone="ok">
          Proposta: {formatCount(suggest.data.clusters_found)} agrupamento(s) encontrados, {formatCount(suggest.data.persisted)}{" "}
          registrados, {formatCount(suggest.data.pending)} pendentes, {formatCount(suggest.data.flagged)} com aviso. Uma
          decisão já tomada não é sobrescrita.
        </Notice>
      ) : null}
      {suggest.error ? <ErrorState error={suggest.error} /> : null}

      {approvedNotSelected.length > 0 ? (
        <Notice tone="warn" as="div" className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-(--color-warn)">
            <strong>{formatCount(approvedNotSelected.length)}</strong> agrupamento(s) aprovado(s) nesta página{" "}
            <strong>ainda não foram mesclados</strong>: aprovar registra a intenção, e só a aplicação absorve as tags.
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
        </Notice>
      ) : null}

      {fulfilled.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md bg-black/[0.02] px-3 py-2 ring-1 ring-(--color-line)">
          <span className="text-xs text-(--color-muted)">
            <strong>{formatCount(fulfilled.length)}</strong> agrupamento(s) aprovado(s) nesta página{" "}
            <strong>já não têm o que absorver</strong>: os membros foram mesclados por outra mesclagem (ou excluídos por
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
        <Notice tone="accent" as="div" className="flex flex-wrap items-center gap-2">
          <span className="text-xs">
            {formatCount(selected.length)} agrupamento(s) selecionado(s) para aplicar
          </span>
          <Button
            size="sm"
            variant="primary"
            disabled={apply.isPending || selected.length > MAX_BATCH}
            title={selected.length > MAX_BATCH ? `O lote aceita no máximo ${MAX_BATCH} agrupamentos.` : undefined}
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
        </Notice>
      ) : null}

      {apply.error ? <ErrorState error={apply.error} /> : null}
      {batch ? (
        <Notice tone="ok" as="div" className="grid gap-1">
          <p className="font-medium text-(--color-ok)">
            {formatCount((batch.applied ?? []).length)} agrupamento(s) aplicado(s)
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
        </Notice>
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
          hint="Rode 'Propor Agrupamentos' para registrar os pares acima do limiar. A proposta não mescla nada: ela só escreve a pergunta."
          action={
            <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
              Propor Agrupamentos
            </Button>
          }
        />
      ) : null}

      {closeEdited.error ? <ErrorState error={closeEdited.error} /> : null}
      {lastEdited ? (
        <MergeOutcome
          label={`Agrupamento #${lastEdited.proposalId} editado e fechado como rejeitado`}
          outcome={lastEdited.outcome}
        />
      ) : null}

      <ul className="grid gap-2">
        {items.map((proposal) => (
          <li key={proposal.proposal_id} className="grid gap-2">
            <ProposalCard
              proposal={proposal}
              editing={editing?.proposal_id === proposal.proposal_id}
              onEdit={() => setEditing(editing?.proposal_id === proposal.proposal_id ? null : proposal)}
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
            {/*
              The editor is a *hand merge* of the members that survived the edit, run by the same
              planner the batch uses — so the numbers do not change depending on which door was used.
              The preview inside the panel is the dry run; the machine's agrupamento is closed afterwards.
            */}
            {editing?.proposal_id === proposal.proposal_id ? (
              <TagMergePanel
                members={(proposal.members ?? []).map((member) => ({ tag_id: member.tag_id, name: member.name }))}
                initialCanonicalId={proposal.canonical_id ?? undefined}
                title={`Editar e aplicar o agrupamento #${proposal.proposal_id}`}
                hint="Desmarque a tag que não pertence ao conjunto e escolha a canônica. Aplicar mescla a seleção revisada pelo mesmo planejador do lote, registra no ledger — e fecha esta proposta como rejeitada, porque a pergunta da máquina foi respondida de outro jeito."
                onMerged={(outcome) => {
                  // The report goes to the screen: this row is about to leave the SUGGESTED filter.
                  setLastEdited({ proposalId: proposal.proposal_id, outcome });
                  setEditing(null);
                  closeEdited.mutate(proposal);
                  invalidate();
                }}
                onClose={() => setEditing(null)}
              />
            ) : null}
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
          {/*
            The search is server-side and covers both sides of each entry: the ledger only grows, and a
            box that filtered the loaded page would say "não está aqui" for a merge that happened.
          */}
          <Input
            className="max-w-xs"
            value={logTerm}
            placeholder="buscar por grafia absorvida ou canônica…"
            onChange={(event) => setLogTerm(event.target.value)}
          />
          {log.isPending ? <Spinner label="Lendo o ledger…" /> : null}
          {log.error ? <ErrorState error={log.error} /> : null}
          {log.data && (log.data.items ?? []).length === 0 ? (
            <EmptyState
              title={logTerm.trim() ? `Nenhum merge para “${logTerm.trim()}”` : "Nenhum merge aplicado ainda"}
              hint={
                logTerm.trim()
                  ? "A busca cobre as duas grafias de cada linha: a absorvida e a canônica."
                  : "O ledger registra cada tag absorvida, com o antes."
              }
            />
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
          {/*
            The footer appears whenever there is something to say: more rows below, or a search that
            matched. A filtered ledger that shows one row and no count leaves the archivist wondering
            whether the filter ran.
          */}
          {log.data && (log.data.total > (log.data.items ?? []).length || settledLogTerm.trim()) ? (
            <div className="flex items-center gap-2">
              {log.data.total > (log.data.items ?? []).length ? (
                <Button size="sm" variant="ghost" onClick={() => setLogLimit((current) => current + MERGE_LOG_PAGE_SIZE)}>
                  ver mais
                </Button>
              ) : null}
              <span className="text-xs text-(--color-muted)">
                mostrando {formatCount((log.data.items ?? []).length)} de {formatCount(log.data.total)}{" "}
                {settledLogTerm.trim() ? "merge(s) que casam com a busca" : "merge(s) aplicado(s)"}
              </span>
            </div>
          ) : null}
        </CardBody>
      </Card>

    </div>
  );
}

/**
 * One agrupamento, with the evidence and the two decisions that are possible about it.
 *
 * The preview is a step, not a decoration: ``category_would_be_lost`` is the only warning that the
 * merge would destroy a classification, and it has to be seen **before** the verdict, because
 * approving records an intent that the next suggestion run will not overwrite.
 */
function ProposalCard({
  proposal,
  selected,
  editing,
  onToggle,
  onApproved,
  onEdit,
}: {
  proposal: TagMergeProposal;
  selected: boolean;
  editing: boolean;
  onToggle: (checked: boolean) => void;
  onApproved: () => void;
  onEdit: () => void;
}) {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<MergePreview | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const decide = useMutation({
    mutationFn: (status: "APPROVED" | "REJECTED") =>
      decideMergeProposal(proposal.proposal_id, { status, note: null }),
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
              incluir no lote de aplicação
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
            {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
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
          {/*
            Editing is offered only while there is still a member to absorb: an applied agrupamento has no
            tags left to unify, and "editar" there would open a panel over names that no longer exist.
          */}
          {proposal.applicable ? (
            <Button
              size="sm"
              variant={editing ? "primary" : "secondary"}
              onClick={onEdit}
              title="Tirar membros do agrupamento antes de mesclar"
            >
              {editing ? "fechando edição" : "editar"}
            </Button>
          ) : null}
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
            <p className="font-medium">Nada foi escrito ainda. A aplicação usa este mesmo planejador.</p>
            <p className="text-(--color-muted)">
              {formatCount(preview.documents_updated)} documento(s) atualizado(s) ·{" "}
              {formatCount(preview.links_rewritten)} vínculo(s) reescrito(s) ·{" "}
              {formatCount((preview.tags_deleted ?? []).length)} tag(s) absorvida(s)
            </p>
            <ul className="text-(--color-muted)">
              {(preview.tags_deleted ?? []).map((impact) => (
                <li key={impact.tag_id}>
                  {impact.name} ({formatCount(impact.document_count)} doc
                  {impact.macro_category_id ? `, categoria ${impact.macro_category_id}` : ""})
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
              <Notice tone="danger">
                Esta mesclagem <strong>exclui uma classificação de assunto</strong>: um dos membros está numa categoria que
                a canônica não tem.
              </Notice>
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
      <Notice tone="warn" className="max-w-3xl">
        <strong>Banir não exclui nada.</strong> Banir registra que o termo não vale; a <strong>purga</strong> é o passo
        que exclui as tags com esse nome — e ela <strong>não tem desfazer</strong>: o merge guarda o estado anterior e
        restaura, a purga não. Por isso ela vem sempre depois de conferir o impacto.
      </Notice>

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
          hint="Banir um termo o tira do eixo escolhido. Nada é excluído por banir: a purga é um passo separado, abaixo."
        />
      ) : null}

      {words.length > 0 ? (
        <Card>
          <CardHeader className="text-sm font-semibold">Termos banidos</CardHeader>
          <CardBody>
            {/*
              A searchable ledger and not a flat column: 200 banned terms is already past the point
              where scrolling to find one is reasonable, and the list only grows.
            */}
            <LedgerList
              items={words}
              keyOf={(item) => item.word}
              termOf={(item) => [item.word, labelOf(STOPWORD_SCOPE_LABEL, item.scope)]}
              searchPlaceholder="buscar termo banido…"
              nounSingular="termo banido"
              nounPlural="termos banidos"
              emptyTitle="Nenhum termo banido"
              emptyHint="Banir um termo o tira do eixo escolhido. Nada é excluído por banir: a purga é um passo separado, abaixo."
              renderItem={(item) => (
                <div className="flex items-center justify-between gap-3 py-1.5">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate">{item.word}</span>
                    <Badge
                      tone={item.scope === "ENTITY" ? "neutral" : "accent"}
                      title={STOPWORD_SCOPE_HINT[item.scope]}
                    >
                      {labelOf(STOPWORD_SCOPE_LABEL, item.scope)}
                    </Badge>
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={unban.isPending}
                    onClick={() => unban.mutate(item.word)}
                  >
                    {ACTION.unban.label}
                  </Button>
                </div>
              )}
            />
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
              {ban.isPending ? ACTION.ban.pending : ACTION.ban.label}
            </Button>
          </div>
          <p className="text-xs text-(--color-muted)">{STOPWORD_SCOPE_HINT[draftScope]}</p>
          {ban.error ? <ErrorState error={ban.error} /> : null}
          {unban.error ? <ErrorState error={unban.error} /> : null}
        </CardBody>
      </Card>

      <Card className="ring-(--color-danger)/30">
        <CardHeader className="text-sm font-semibold text-(--color-danger)">Excluir as tags banidas</CardHeader>
        <CardBody className="grid gap-3">
          <p className="text-xs text-(--color-muted)">
            A purga exclui toda tag cujo nome seja um termo banido nos eixos <code>TAG</code> ou <code>ALL</code>. Os
            vínculos caem junto e a classificação da tag vai embora. <strong>Não há desfazer.</strong>
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={dryRun.isPending || purge.isPending} onClick={() => dryRun.mutate()}>
              {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
            </Button>
            <Button
              variant="danger"
              disabled={!preview || preview.total_tags === 0 || purge.isPending}
              title={preview ? undefined : "O impacto é obrigatório: confira o que seria excluído primeiro."}
              onClick={() => purge.mutate()}
            >
              {purge.isPending
                ? ACTION.exclude.pending
                : preview
                  ? `Excluir ${formatCount(preview.total_tags)} tag(s)`
                  : "Excluir (confira antes)"}
            </Button>
          </div>

          {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
          {purge.error ? <ErrorState error={purge.error} /> : null}

          {preview ? (
            <Notice tone="danger" as="div" className="grid gap-2">
              <p>
                Nada foi excluído ainda. Seriam <strong>{formatCount(preview.total_tags)} tag(s)</strong> em{" "}
                <strong>{formatCount(preview.total_documents)} descrição(ões)</strong>.
              </p>
              {(preview.stopwords ?? []).length > 0 ? (
                <p className="text-(--color-muted)">
                  termos que a purga alcança: <code>{(preview.stopwords ?? []).join(", ")}</code>
                </p>
              ) : null}
              {preview.total_tags === 0 ? (
                <p className="text-(--color-muted)">
                  Nenhuma tag do acervo tem um desses nomes — não há o que excluir.
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
            </Notice>
          ) : null}

          {purged !== null ? (
            <Notice tone="ok">
              {formatCount(purged)} tag(s) excluída(s). Isto <strong>não</strong> aparece no ledger de merges: não há
              estado anterior guardado para restaurar.
            </Notice>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

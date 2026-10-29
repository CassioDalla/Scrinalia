import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import {
  applyMergeBatch,
  banStopwords,
  curateTag,
  fetchMergeProposals,
  decideMergeProposal,
  mergeTags,
  previewMerge,
  previewTagPair,
  suggestMergeProposals,
  undoMerge,
  type BatchMergeResponse,
  type MacroCategory,
  type MergePreview,
  type MergeReason,
  type MergeResponse,
  type ProposalStatus,
  type StopwordsScope,
  type TagCatalogRow,
  type TagCatalogState,
  type TagMergeProposal,
  type TagPairSimilarity,
} from "@/api/client";
import { queries, CATALOG_PAGE_SIZE, MERGE_LOG_PAGE_SIZE, PROPOSALS_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { PageBody } from "@/components/layout/PageBody";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { Trans } from "@/i18n/trans";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDateTime } from "@/lib/format";
import { asBoolean, asEnum, asNumber, asString } from "@/lib/search";
import { useDebounced } from "@/lib/useDebounced";
import {
  CATALOG_STATE_HINT,
  CATALOG_STATE_LABEL,
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
import { Hint } from "@/components/ui/Hint";

const routeApi = getRouteApi("/assuntos/tags");

const TABS = [
  { id: "relevancia", key: "relevance" },
  { id: "similaridade", key: "similarity" },
  { id: "propostas", key: "proposals" },
  /**
   * The decision queue, and the tab the home screen's cards open.
   *
   * Appended rather than placed first: the four analysis tabs have had this order since the screen
   * existed, and the cards carry ``aba`` explicitly — a deep link does not depend on the default.
   */
  { id: "classificar", key: "classify" },
] as const;

/**
 * The tab id that moved out, defined once.
 *
 * `stopwords` left the strip in #232: the blocked spellings are `/assuntos/grafias`, a screen of
 * their own beside *Não é Assunto*, because this screen's description never mentioned that its
 * fourth tab held the only write that deletes a tag. The id stays accepted here so the route's
 * `beforeLoad` can send a bookmark to the new screen instead of silently opening `Relevância`, which
 * is exactly what the old `Tags` button on the verdict screen did.
 */
export const LEGACY_STOPWORDS_ABA = "stopwords";
const LEGACY_ABAS = [LEGACY_STOPWORDS_ABA];
const ABAS: string[] = [...TABS.map((tab) => tab.id), ...LEGACY_ABAS];

const REASONS: MergeReason[] = ["TRIGRAM", "PLURAL", "MIXED"];
const SCOPE_VALUES: StopwordsScope[] = ["TAG", "ENTITY", "ALL"];
const CATALOG_STATES: TagCatalogState[] = ["ALL", "PENDING", "NOT_SUBJECT", "LOW_CONFIDENCE"];

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
  /** The catalogue's filter by the state of the subject decision. */
  subject_state?: TagCatalogState;
  /** The drawer the catalogue is restricted to, when the archivist picked one. */
  cat?: number;
  /** The catalogue's own search box. Separate from ``nome``, which filters the similarity pairs. */
  termo?: string;
};

export function validateTagsSearch(search: Record<string, unknown>): TagsSearch {
  return {
    aba: asEnum(search.aba, ABAS) ?? "relevancia",
    metodo: asEnum(search.metodo, ["count", "tfidf"]) ?? "count",
    limiar: asNumber(search.limiar) ?? 0.65,
    alvo: asString(search.alvo),
    nome: asString(search.nome),
    status: asEnum(search.status, STATUSES),
    motivo: asEnum(search.motivo, REASONS),
    min: asNumber(search.min),
    flag: asBoolean(search.flag),
    offset: asNumber(search.offset),
    // Only the decision tab has a state, and it opens on the queue the home screen counts; keeping
    // the key off the other four tabs is what stops the address bar from carrying a filter that
    // nothing on screen reads.
    subject_state:
      asEnum(search.subject_state, CATALOG_STATES) ?? (search.aba === "classificar" ? "PENDING" : undefined),
    cat: asNumber(search.cat),
    termo: asString(search.termo),
  };
}

/**
 * The tag catalog: what weighs most, what looks duplicated, and the queue of merge decisions.
 *
 * The three questions live in one route because they are one conversation — the archivist sees that
 * ``alvenarias`` weighs little, finds its near-duplicate, and decides whether to absorb it. The
 * active question is in the URL, so a colleague can be sent the exact list.
 *
 * The blocked spellings used to be the fourth subtab, and they are `/assuntos/grafias` since #232 —
 * a screen of their own, beside *Não é Assunto*, because this page never described the only write
 * that deletes a tag. What stayed here is the ban as a consequence of a merge decision: the axis is
 * chosen before the click, banning a word deletes nothing, and the exclusion of the tags lives on
 * that other screen, behind its own preview.
 */
export function TagsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const messages = useCopy();
  const tabs = TABS.map((tab) => ({ id: tab.id, label: messages.pages.tags.tabs[tab.key] }));

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
          items={tabs}
          active={search.aba ?? "relevancia"}
          onChange={(id) => patch({ aba: id })}
        />
      </div>

      <PageBody>
        {search.aba === "similaridade" ? (
          <SimilarityTab search={search} patch={patch} />
        ) : search.aba === "propostas" ? (
          <ProposalsTab search={search} patch={patch} />
        ) : search.aba === "classificar" ? (
          <ClassificarTab search={search} patch={patch} />
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
  const messages = useCopy();
  const method = search.metodo ?? "count";
  const [limit, setLimit] = useState(30);
  const relevance = useQuery(queries.tagRelevance(method, limit));

  const payload = relevance.data?.payload ?? [];

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select className="w-48" value={method} onChange={(event) => patch({ metodo: event.target.value as "count" | "tfidf" })}>
          <option value="count">
            <Trans
              text={messages.pages.tags.relevance.countOption}
              values={{ count: <strong>{messages.pages.tags.relevance.count}</strong> }}
            />
          </option>
          <option value="tfidf">{messages.pages.tags.relevance.specificityOption}</option>
        </Select>
        <Select className="w-36" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
          {[30, 50, 100, 200].map((value) => (
            <option key={value} value={value}>
              {fill(messages.pages.tags.relevance.perPage, { count: value })}
            </option>
          ))}
        </Select>
        <Hint label={messages.pages.tags.relevance.hintLabel} className="max-w-3xl text-xs text-(--color-muted)">
          <Trans
            text={messages.pages.tags.relevance.hint}
            values={{
              usage: <strong>{messages.pages.tags.relevance.usage}</strong>,
              specificity: <strong>{messages.pages.tags.relevance.specificityWord}</strong>,
            }}
          />
        </Hint>
      </div>

      {relevance.error ? <ErrorState error={relevance.error} /> : null}
      {relevance.isPending ? <Spinner /> : null}

      {payload.length > 0 ? (
        <Card>
          <CardBody className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-(--color-line) text-xs text-(--color-muted)">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">{messages.pages.tags.columns.tag}</th>
                  {method === "count" ? (
                    <th className="px-3 py-2 text-right font-medium">{messages.pages.tags.columns.documents}</th>
                  ) : (
                    <>
                      <th className="px-3 py-2 text-right font-medium">{messages.pages.tags.columns.frequency}</th>
                      <th className="px-3 py-2 text-right font-medium">{messages.pages.tags.columns.rarity}</th>
                      <th className="px-3 py-2 text-right font-medium">{messages.pages.tags.columns.specificity}</th>
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
  const messages = useCopy();
  const queryClient = useQueryClient();
  const threshold = search.limiar ?? 0.65;
  const [showAll, setShowAll] = useState(false);
  /** One row opened by its own button: the panel renders right under it. */
  const [openPair, setOpenPair] = useState<TagPairSimilarity | null>(null);
  /** Tags marked across rows, for the case the pair list cannot express: one merge out of many rows. */
  const [marked, setMarked] = useState<MergeCandidate[]>([]);
  const [clusterOpen, setClusterOpen] = useState(false);
  const [lastMerge, setLastMerge] = useState<{ label: string; outcome: MergeResponse } | null>(null);
  /** The axis the ban goes to, chosen before the click: ``domain_stopwords.word`` is unique. */
  const [banScope, setBanScope] = useState<StopwordsScope>("TAG");
  const [lastBan, setLastBan] = useState<{ written: number; scope: StopwordsScope } | null>(null);

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
   * Bans the whole selection, in one call.
   *
   * The route already takes a list and the marks *are* the list: twenty spellings that all mean
   * "this is not worth considering" are twenty trips to the blocked-spellings screen and one click
   * here. The axis is chosen before the click because a ban is *from* one axis —
   * `domain_stopwords.word` is unique, so re-banning moves the term instead of adding a second row —
   * and the NER veto is not the subject veto.
   *
   * Banning **deletes nothing**: the tags stay in the collection, linked and reachable, and the
   * step that removes them is the exclusion of tags, in `Grafias bloqueadas`, behind its own
   * preview. That is why the marks are **not** cleared: unlike a merge, this write took no row
   * away, so the selection is still there and the merge it was made for is still possible.
   */
  const banMarked = useMutation({
    mutationFn: () => banStopwords({ words: marked.map((member) => member.name), scope: banScope }),
    onSuccess: (written) => {
      setLastBan({ written: written.created, scope: banScope });
      // The banned terms are another tab's read, and the axis is part of its query key.
      void queryClient.invalidateQueries({ queryKey: ["taxonomy", "stopwords"] });
      invalidate();
    },
  });

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
    setLastMerge({ label: messages.pages.tags.similarity.mergeApplied, outcome });
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
          <span className="text-(--color-muted)">{messages.pages.tags.filters.threshold}</span>
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
          placeholder={messages.pages.tags.similarity.filterPlaceholder}
          defaultValue={search.nome ?? ""}
          onChange={(event) => patch({ nome: event.target.value || undefined })}
        />
      </div>

      <p className="max-w-3xl text-xs text-(--color-muted)">
        {messages.pages.tags.similarity.intro}
      </p>

      {similar.error ? <ErrorState error={similar.error} /> : null}
      {similar.isPending ? <Spinner /> : null}

      {lastMerge ? <MergeOutcome label={lastMerge.label} outcome={lastMerge.outcome} /> : null}

      {lastBan ? (
        <Notice tone="ok">
          <Trans
            text={messages.pages.tags.similarity.banNotice}
            values={{
              banned: (
                <strong>
                  {fill(messages.pages.tags.similarity.banCount, {
                    count: formatCount(lastBan.written),
                    scope: labelOf(STOPWORD_SCOPE_LABEL, lastBan.scope).toLowerCase(),
                  })}
                </strong>
              ),
              nothing: <strong>{messages.pages.tags.similarity.notExcludes}</strong>,
              place: <Link to="/assuntos/grafias" className="font-semibold underline underline-offset-2">{messages.screens.blockedSpellings.label}</Link>,
            }}
          />
        </Notice>
      ) : null}
      {banMarked.error ? <ErrorState error={banMarked.error} /> : null}

      {/*
        Two rows at once is a different operation from one row, and it gets the panel in the place the
        archivist suggested for it: the top, because there is no single row it belongs under.
      */}
      {clusterOpen && marked.length >= 2 ? (
        <TagMergePanel
          members={marked}
          title={fill(messages.pages.tags.similarity.mergeMarkedTitle, { count: formatCount(marked.length) })}
          hint={messages.pages.tags.similarity.mergeMarkedHint}
          onMerged={afterMerge}
          onClose={closePanel}
        />
      ) : null}

      {similar.data && pairs.length === 0 ? (
        <EmptyState
          title={messages.pages.tags.similarity.noPairsTitle}
          hint={messages.pages.tags.similarity.noPairsHint}
        />
      ) : null}

      {shown.length > 0 ? (
        <Card>
          <CardHeader className="flex items-center justify-between text-xs text-(--color-muted)">
            <span>
              {term
                ? fill(messages.pages.tags.similarity.pairCountTerm, {
                    count: formatCount(visible.length),
                    term: search.nome ?? "",
                    total: formatCount(pairs.length),
                  })
                : fill(messages.pages.tags.similarity.pairCountAll, {
                    count: formatCount(visible.length),
                    total: formatCount(pairs.length),
                  })}
            </span>
            {marked.length > 0 ? (
              <Button size="sm" variant="ghost" onClick={clearMarked}>
                {fill(messages.pages.tags.similarity.clearMarks, { count: formatCount(marked.length) })}
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
                        title={messages.pages.tags.similarity.markRowTitle}
                        aria-label={fill(messages.pages.tags.similarity.markPairAria, {
                          first: pair.name_1,
                          second: pair.name_2,
                        })}
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
                        {openPair === pair ? ACTION.close.label : messages.pages.tags.similarity.mergeArrow}
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
                        title={messages.pages.tags.similarity.mergeTwoTitle}
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
              {fill(messages.pages.tags.similarity.markedBar, {
                tags: formatCount(marked.length),
                rows: formatCount(countRows(marked, pairs)),
              })}
            </span>
            <Button size="sm" variant="primary" onClick={() => setClusterOpen(true)}>
              {messages.pages.tags.merge.defaultTitle}
            </Button>
            {/*
              The other decision the same selection makes possible, and the one the marks were
              already good for: a list of spellings that all mean the same thing to ban. It is a
              different kind of write from the merge, so it sits behind a divider and names its axis
              before the click.
            */}
            <span className="h-4 w-px bg-white/20" aria-hidden />
            <Select
              // The bar is ``text-white`` and the control is ``bg-white``: without the explicit ink
              // colour the option text renders white on white — measured on the other bar.
              className="w-40 text-(--color-ink)"
              value={banScope}
              disabled={banMarked.isPending}
              title={STOPWORD_SCOPE_HINT[banScope]}
              aria-label={messages.pages.tags.similarity.banScopeAria}
              onChange={(event) => setBanScope(event.target.value as StopwordsScope)}
            >
              {SCOPE_VALUES.map((scope) => (
                <option key={scope} value={scope}>
                  {labelOf(STOPWORD_SCOPE_LABEL, scope)}
                </option>
              ))}
            </Select>
            <Button
              size="sm"
              variant="secondary"
              disabled={banMarked.isPending || marked.length === 0}
              title={fill(messages.pages.tags.similarity.banTitle, {
                place: messages.screens.blockedSpellings.label,
              })}
              onClick={() => banMarked.mutate()}
            >
              {banMarked.isPending
                ? ACTION.ban.pending
                : fill(messages.pages.tags.similarity.banMarked, { count: formatCount(marked.length) })}
            </Button>
            <button className="text-xs text-white/70 hover:text-white" onClick={clearMarked}>
              {messages.pages.tags.clear}
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
  const messages = useCopy();
  return (
    <Notice tone="ok">
      <Trans
        text={messages.pages.tags.merge.outcome}
        values={{
          label: <strong>{label}</strong>,
          documents: formatCount(outcome.documents_updated),
          tags: formatCount(outcome.tags_deleted),
          ids: <code>{(outcome.merge_ids ?? []).join(", ") || "—"}</code>,
        }}
      />
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
  const messages = useCopy();
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
        <p className="text-sm font-semibold">{title ?? messages.pages.tags.merge.defaultTitle}</p>
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
                  title={out ? messages.pages.tags.merge.returnToGroup : messages.pages.tags.merge.removeFromGroup}
                  aria-label={fill(messages.pages.tags.merge.includeInGroup, { name: member.name })}
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
                  title={messages.pages.tags.merge.keepSpelling}
                />
                <span className={isCanonical ? "font-medium" : "text-(--color-muted)"}>
                  {member.name} <code className="text-[10px]">#{member.tag_id}</code>
                  {out
                    ? messages.pages.tags.merge.outOfGroup
                    : isCanonical
                      ? messages.pages.tags.merge.keptCanonical
                      : messages.pages.tags.merge.absorbed}
                </span>
              </div>
            );
          })}
        </div>

        <p className="text-xs text-(--color-muted)">
          {messages.pages.tags.merge.explain}
        </p>

        {preview.isPending ? <Spinner label={messages.pages.tags.merge.checkingImpact} /> : null}
        {preview.error ? <ErrorState error={preview.error} /> : null}

        {preview.data ? (
          <div className="grid gap-1 rounded-md bg-black/[0.02] p-3 text-xs ring-1 ring-(--color-line)">
            <p className="font-medium">{messages.pages.tags.merge.nothingWritten}</p>
            <p className="text-(--color-muted)">
              {fill(messages.pages.tags.merge.counts, {
                documents: formatCount(preview.data.documents_updated),
                links: formatCount(preview.data.links_rewritten),
                tags: formatCount(tagsDeleted.length),
              })}
            </p>
            <ul className="text-(--color-muted)">
              {tagsDeleted.map((impact) => (
                <li key={impact.tag_id}>
                  <Trans
                    text={messages.pages.tags.merge.impactLine}
                    values={{
                      name: impact.name,
                      id: <code className="text-[10px]">#{impact.tag_id}</code>,
                      documents: formatCount(impact.document_count),
                      category: impact.macro_category_id
                        ? fill(messages.pages.tags.merge.categorySuffix, {
                            category: categoryName(impact.macro_category_id),
                          })
                        : "",
                    }}
                  />
                </li>
              ))}
            </ul>
            {(preview.data.synonyms_created ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                <Trans
                  text={messages.pages.tags.merge.synonymsCreated}
                  values={{ list: <code>{(preview.data.synonyms_created ?? []).join(", ")}</code> }}
                />
              </p>
            ) : null}
            {(preview.data.synonyms_repointed ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                <Trans
                  text={messages.pages.tags.merge.synonymsRepointed}
                  values={{ list: <code>{(preview.data.synonyms_repointed ?? []).join(", ")}</code> }}
                />
              </p>
            ) : null}
            {preview.data.category_would_be_lost ? (
              <Notice tone="danger">
                <Trans
                  text={messages.pages.tags.merge.lostCategory}
                  values={{
                    excludes: <strong>{messages.pages.tags.merge.lostCategoryStrong}</strong>,
                    drawers: <strong>{lostDrawers.join(", ") || "—"}</strong>,
                  }}
                />
              </Notice>
            ) : null}
          </div>
        ) : null}

        <Notice tone="ok">
          <Trans
            text={messages.pages.tags.merge.undoNotice}
            values={{ hasUndo: <strong>{messages.pages.tags.merge.hasUndo}</strong> }}
          />
        </Notice>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={!preview.data || merge.isPending || outcome !== null || included.length < 2}
            title={
              included.length < 2
                ? messages.pages.tags.merge.atLeastTwo
                : preview.data
                  ? undefined
                  : messages.pages.tags.merge.checkImpactFirst
            }
            onClick={() => merge.mutate()}
          >
            {merge.isPending
              ? ACTION.merge.pending
              : absorbed.length === 1
                ? fill(messages.pages.tags.merge.mergeOneIn, {
                    name: absorbed[0]?.name ?? "",
                    canonical: nameOf(canonicalId),
                  })
                : fill(messages.pages.tags.merge.mergeManyIn, {
                    count: formatCount(absorbed.length),
                    canonical: nameOf(canonicalId),
                  })}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            {outcome ? ACTION.close.label : ACTION.cancel.label}
          </Button>
        </div>

        {merge.error ? <ErrorState error={merge.error} /> : null}

        {outcome ? (
          <Notice tone="ok">
            <Trans
              text={messages.pages.tags.merge.done}
              values={{
                documents: formatCount(outcome.documents_updated),
                tags: formatCount(outcome.tags_deleted),
                ids: <code>{(outcome.merge_ids ?? []).join(", ") || "—"}</code>,
              }}
            />
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
  const messages = useCopy();
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
          note: messages.pages.tags.proposals.archiveNote,
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
        note: fill(messages.pages.tags.proposals.editedNote, {
          count: formatCount((proposal.members ?? []).length),
        }),
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
          {suggest.isPending
            ? messages.pages.tags.proposals.suggesting
            : messages.pages.tags.proposals.suggest}
        </Button>
        <label className="flex items-center gap-2 text-xs">
          <span className="text-(--color-muted)">{messages.pages.tags.filters.threshold}</span>
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
          <option value="">{messages.pages.tags.filters.allStatuses}</option>
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
          <option value="">{messages.pages.tags.filters.anyReason}</option>
          {REASONS.map((reason) => (
            <option key={reason} value={reason}>
              {labelOf(MERGE_REASON_LABEL, reason)}
            </option>
          ))}
        </Select>
        <Input
          type="number"
          className="w-32"
          placeholder={messages.pages.tags.filters.minDocs}
          defaultValue={search.min ?? ""}
          onChange={(event) => patch({ min: event.target.value ? Number(event.target.value) : undefined })}
        />
        <Button
          size="sm"
          variant={search.flag ? "primary" : "secondary"}
          onClick={() => patch({ flag: search.flag ? undefined : true })}
        >
          {messages.pages.tags.filters.onlyFlagged}
        </Button>
      </div>

      {suggest.data ? (
        <Notice tone="ok">
          {fill(messages.pages.tags.proposals.suggestNotice, {
            found: formatCount(suggest.data.clusters_found),
            persisted: formatCount(suggest.data.persisted),
            pending: formatCount(suggest.data.pending),
            flagged: formatCount(suggest.data.flagged),
          })}
        </Notice>
      ) : null}
      {suggest.error ? <ErrorState error={suggest.error} /> : null}

      {approvedNotSelected.length > 0 ? (
        <Notice tone="warn" as="div" className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-(--color-warn)">
            <Trans
              text={messages.pages.tags.proposals.approvedNotice}
              values={{
                count: <strong>{formatCount(approvedNotSelected.length)}</strong>,
                notMerged: <strong>{messages.pages.tags.proposals.notMerged}</strong>,
              }}
            />
          </span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setSelected((current) => [...new Set([...current, ...approvedNotSelected.map((p) => p.proposal_id)])])}
          >
            {messages.pages.tags.proposals.includeApproved}
          </Button>
          <Button size="sm" disabled={selectAllApproved.isPending} onClick={() => selectAllApproved.mutate()}>
            {selectAllApproved.isPending
              ? messages.pages.tags.proposals.searching
              : messages.pages.tags.proposals.selectAllApproved}
          </Button>
        </Notice>
      ) : null}

      {fulfilled.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md bg-black/[0.02] px-3 py-2 ring-1 ring-(--color-line)">
          <span className="text-xs text-(--color-muted)">
            <Trans
              text={messages.pages.tags.proposals.fulfilledNotice}
              values={{
                count: <strong>{formatCount(fulfilled.length)}</strong>,
                nothing: <strong>{messages.pages.tags.proposals.nothingToAbsorb}</strong>,
              }}
            />
          </span>
          <Button
            size="sm"
            variant="ghost"
            disabled={decideMany.isPending}
            onClick={() => decideMany.mutate(fulfilled.map((proposal) => proposal.proposal_id))}
          >
            {messages.pages.tags.proposals.archiveFulfilled}
          </Button>
        </div>
      ) : null}

      {selected.length > 0 ? (
        <Notice tone="accent" as="div" className="flex flex-wrap items-center gap-2">
          <span className="text-xs">
            {fill(messages.pages.tags.proposals.selectedCount, { count: formatCount(selected.length) })}
          </span>
          <Button
            size="sm"
            variant="primary"
            disabled={apply.isPending || selected.length > MAX_BATCH}
            title={
              selected.length > MAX_BATCH
                ? fill(messages.pages.tags.proposals.batchLimitTitle, { max: MAX_BATCH })
                : undefined
            }
            onClick={() => apply.mutate()}
          >
            {apply.isPending ? ACTION.apply.pending : messages.pages.tags.proposals.applyBatch}
          </Button>
          {selected.length > MAX_BATCH ? (
            <span className="text-xs text-(--color-danger)">
              {fill(messages.pages.tags.proposals.batchTooMany, {
                count: formatCount(selected.length),
                max: MAX_BATCH,
              })}
            </span>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            {messages.pages.tags.proposals.clearSelection}
          </Button>
        </Notice>
      ) : null}

      {apply.error ? <ErrorState error={apply.error} /> : null}
      {batch ? (
        <Notice tone="ok" as="div" className="grid gap-1">
          <p className="font-medium text-(--color-ok)">
            {fill(messages.pages.tags.proposals.batchApplied, {
              count: formatCount((batch.applied ?? []).length),
            })}
            {(batch.skipped ?? []).length > 0
              ? fill(messages.pages.tags.proposals.batchSkipped, {
                  count: formatCount((batch.skipped ?? []).length),
                })
              : ""}
            {fill(messages.pages.tags.proposals.batchFailed, {
              count: formatCount((batch.failed ?? []).length),
            })}
          </p>
          {(batch.applied ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-muted)">
              {fill(messages.pages.tags.proposals.appliedLine, {
                id: entry.proposal_id,
                documents: formatCount(entry.documents_updated),
                tags: formatCount(entry.tags_deleted),
                ids: (entry.merge_ids ?? []).join(", "),
              })}
            </p>
          ))}
          {(batch.skipped ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-muted)">
              {fill(messages.pages.tags.proposals.skippedLine, { id: entry.proposal_id, error: entry.error })}
            </p>
          ))}
          {(batch.failed ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-danger)">
              {fill(messages.pages.tags.proposals.failedLine, { id: entry.proposal_id, error: entry.error })}
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
          title={messages.pages.tags.proposals.emptyTitle}
          hint={messages.pages.tags.proposals.emptyHint}
          action={
            <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
              {messages.pages.tags.proposals.suggest}
            </Button>
          }
        />
      ) : null}

      {closeEdited.error ? <ErrorState error={closeEdited.error} /> : null}
      {lastEdited ? (
        <MergeOutcome
          label={fill(messages.pages.tags.proposals.editedClosed, { id: lastEdited.proposalId })}
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
                title={fill(messages.pages.tags.proposals.editMergeTitle, { id: proposal.proposal_id })}
                hint={messages.pages.tags.proposals.editMergeHint}
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
            {messages.common.previous}
          </Button>
          <span className="text-xs text-(--color-muted)">
            {fill(messages.common.range, {
              from: formatCount(offset + 1),
              to: formatCount(Math.min(offset + PROPOSALS_PAGE_SIZE, total)),
              total: formatCount(total),
            })}
          </span>
          <Button
            size="sm"
            disabled={offset + PROPOSALS_PAGE_SIZE >= total}
            onClick={() => patch({ offset: offset + PROPOSALS_PAGE_SIZE })}
          >
            {messages.common.next}
          </Button>
        </div>
      ) : null}

      <Card>
        <CardHeader className="text-sm font-semibold">{messages.pages.tags.ledger.title}
          <Hint label={messages.pages.tags.ledger.title} className="text-xs text-(--color-muted)">
            <Trans
              text={messages.pages.tags.ledger.hint}
              values={{ concluded: <strong>{messages.pages.tags.ledger.concluded}</strong> }}
            />
          </Hint>
        </CardHeader>
        <CardBody className="grid gap-2">
          {/*
            The search is server-side and covers both sides of each entry: the ledger only grows, and a
            box that filtered the loaded page would say "não está aqui" for a merge that happened.
          */}
          <Input
            className="max-w-xs"
            value={logTerm}
            placeholder={messages.pages.tags.ledger.searchPlaceholder}
            onChange={(event) => setLogTerm(event.target.value)}
          />
          {log.isPending ? <Spinner label={messages.pages.tags.ledger.reading} /> : null}
          {log.error ? <ErrorState error={log.error} /> : null}
          {log.data && (log.data.items ?? []).length === 0 ? (
            <EmptyState
              title={
                logTerm.trim()
                  ? fill(messages.pages.tags.ledger.emptyTerm, { term: logTerm.trim() })
                  : messages.pages.tags.ledger.emptyNone
              }
              hint={
                logTerm.trim()
                  ? messages.pages.tags.ledger.emptyHintTerm
                  : messages.pages.tags.ledger.emptyHintNone
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
                    {fill(messages.pages.tags.ledger.entryMeta, {
                      documents: formatCount(entry.document_count),
                      date: formatDateTime(entry.changed_at),
                      by: entry.changed_by
                        ? fill(messages.pages.tags.ledger.entryBy, { name: entry.changed_by })
                        : "",
                    })}
                  </span>
                </span>
                {entry.undone_at ? (
                  <Badge tone="neutral">
                    {fill(messages.pages.tags.ledger.undoneAt, { date: formatDateTime(entry.undone_at) })}
                  </Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={undo.isPending}
                    title={messages.pages.tags.ledger.undoTitle}
                    onClick={() => undo.mutate(entry.merge_id)}
                  >
                    {messages.pages.tags.ledger.undo}
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
                  {messages.pages.tags.ledger.seeMore}
                </Button>
              ) : null}
              <span className="text-xs text-(--color-muted)">
                {fill(
                  settledLogTerm.trim()
                    ? messages.pages.tags.ledger.showingFiltered
                    : messages.pages.tags.ledger.showingAll,
                  {
                    shown: formatCount((log.data.items ?? []).length),
                    total: formatCount(log.data.total),
                  },
                )}
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
  const messages = useCopy();
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
            <span className="text-xs text-(--color-muted)">
              {fill(messages.pages.tags.proposal.documents, { count: formatCount(proposal.total_documents) })}
            </span>
          </span>
          {proposal.status === "APPROVED" && proposal.applicable ? (
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={selected} onChange={(event) => onToggle(event.target.checked)} />
              {messages.pages.tags.proposal.includeInBatch}
            </label>
          ) : null}
          {proposal.status === "APPROVED" && !proposal.applicable ? (
            <span
              className="text-xs text-(--color-muted)"
              title={messages.pages.tags.proposal.membersGoneTitle}
            >
              {messages.pages.tags.proposal.noMembers}
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
            {messages.pages.tags.proposal.approve}
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={decide.isPending || proposal.status === "REJECTED"}
            onClick={() => decide.mutate("REJECTED")}
          >
            {messages.pages.tags.proposal.reject}
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
              title={messages.pages.tags.proposal.editTitle}
            >
              {editing ? messages.pages.tags.proposal.editClosing : messages.pages.tags.proposal.edit}
            </Button>
          ) : null}
          {proposal.decided_by || proposal.decision_note ? (
            <span className="text-xs text-(--color-muted)">
              {proposal.decided_by ? fill(messages.pages.tags.proposal.decidedBy, { name: proposal.decided_by }) : ""}
              {proposal.decision_note
                ? fill(messages.pages.tags.proposal.decisionNote, { note: proposal.decision_note })
                : ""}
            </span>
          ) : null}
        </div>

        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
        {decide.error ? <ErrorState error={decide.error} /> : null}

        {preview ? (
          <div className="grid gap-1 rounded-md bg-black/[0.02] p-3 text-xs ring-1 ring-(--color-line)">
            <p className="font-medium">{messages.pages.tags.merge.nothingWritten}</p>
            <p className="text-(--color-muted)">
              {fill(messages.pages.tags.merge.counts, {
                documents: formatCount(preview.documents_updated),
                links: formatCount(preview.links_rewritten),
                tags: formatCount((preview.tags_deleted ?? []).length),
              })}
            </p>
            <ul className="text-(--color-muted)">
              {(preview.tags_deleted ?? []).map((impact) => (
                <li key={impact.tag_id}>
                  {fill(messages.pages.tags.proposal.impactLine, {
                    name: impact.name,
                    documents: formatCount(impact.document_count),
                    category: impact.macro_category_id
                      ? fill(messages.pages.tags.merge.categorySuffix, {
                          category: impact.macro_category_id,
                        })
                      : "",
                  })}
                </li>
              ))}
            </ul>
            {(preview.synonyms_created ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                <Trans
                  text={messages.pages.tags.merge.synonymsCreated}
                  values={{ list: <code>{(preview.synonyms_created ?? []).join(", ")}</code> }}
                />
              </p>
            ) : null}
            {(preview.synonyms_repointed ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                <Trans
                  text={messages.pages.tags.merge.synonymsRepointed}
                  values={{ list: <code>{(preview.synonyms_repointed ?? []).join(", ")}</code> }}
                />
              </p>
            ) : null}
            {preview.category_would_be_lost ? (
              <Notice tone="danger">
                <Trans
                  text={messages.pages.tags.proposal.lostCategory}
                  values={{ excludes: <strong>{messages.pages.tags.merge.lostCategoryStrong}</strong> }}
                />
              </Notice>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

// =============================================================================================
// Classificar — a fila de tags sem decisão de assunto
// =============================================================================================

/**
 * The two destinations, and they are exclusive: a category, or "not a subject". One shape for the
 * selection's action, so the bulk path cannot write something the single row cannot.
 */
type BulkAction = { kind: "category"; categoryId: number } | { kind: "not-subject" };

/**
 * The decision queue of the subject axis: the tab the home screen's two cards open.
 *
 * The read did not exist before it. The relevance lists are a top-N by weight with no notion of
 * state, so a card promising "76 tags without a subject" had no screen that could mark which rows
 * they were — the archivist landed on an unfiltered ranking. Here the state is a filter over the
 * whole catalogue, with the total beside it, and the row is where the decision is taken.
 *
 * There are two destinations because the tag axis is the subject axis (ADR 0013). **Not a subject**
 * silences the classifier and bans the spelling from coming back, which is the durable half of the
 * verdict: ``macro_category_id=null`` alone is overwritten the next time the label set changes. A
 * producer, a place or a person is not a third destination here — the entity axis carries *what it
 * is* (``LOC``/``PER``/``ORG``, what search and diffusion read), and the tag × entity conflict screen
 * settles a spelling that is both. Banning and purging remain the destructive paths in Stopwords.
 */
function ClassificarTab({ search, patch }: { search: TagsSearch; patch: (changes: Partial<TagsSearch>) => void }) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const categories = useQuery(queries.macroCategories());
  const [selected, setSelected] = useState<number[]>([]);
  const [report, setReport] = useState<string | null>(null);

  const state = search.subject_state ?? "PENDING";
  const catalog = useQuery(
    queries.tagCatalog({
      subject_state: state,
      macro_category_id: search.cat,
      term: search.termo,
      offset: search.offset,
    }),
  );

  const items = catalog.data?.items ?? [];
  const total = catalog.data?.total ?? 0;
  const offset = search.offset ?? 0;
  /**
   * Whether the payload on screen belongs to the filter on screen.
   *
   * ``placeholderData`` keeps the previous page while the next one loads, which is right for the
   * rows and wrong for the **counts**: the header would promise the previous filter's total under
   * the new chip, and a filter that answers nothing would render the previous filter's empty state.
   * The rows may lag; the numbers may not.
   */
  const countsAreCurrent = catalog.data !== undefined && !catalog.isPlaceholderData;
  /**
   * Every category, retired ones included: the state `ALL` lists tags that sit in a retired drawer,
   * and a select that only offered the active ones would display "sem categoria" for a tag whose
   * badge above says otherwise. The catalogue screen makes the same choice for the same reason.
   */
  const drawers = categories.data ?? [];

  /**
   * The selection belongs to the rows on screen.
   *
   * A filter or a page change makes the marked tags invisible, and the bar would then write to tags
   * the archivist can no longer see — a batch decision is not something to take blind. Adjusted
   * during render (the pattern React documents for syncing state with a prop) instead of in an
   * effect, which would render one frame with the stale selection.
   */
  const selectionKey = `${state}|${search.cat ?? ""}|${search.termo ?? ""}|${offset}`;
  const [selectionFor, setSelectionFor] = useState(selectionKey);
  if (selectionFor !== selectionKey) {
    setSelectionFor(selectionKey);
    setSelected([]);
  }

  /**
   * A decision about a tag touches four screens: the catalogue it just left, the drawers' weights,
   * every description that carries the tag, and the counters on the home screen.
   */
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "macro-categories"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const curate = useMutation({
    mutationFn: ({ tagId, categoryId }: { tagId: number; categoryId: number | null }) =>
      curateTag(tagId, { macro_category_id: categoryId, note: null }),
    onSuccess: (result) => {
      setReport(
        result.macro_category_name
          ? fill(messages.pages.tags.classify.reportCategory, {
              name: result.name,
              category: result.macro_category_name,
            })
          : fill(messages.pages.tags.classify.reportNotSubject, { name: result.name }),
      );
      invalidate();
    },
  });

  /**
   * The same decision over a selection, one request per tag.
   *
   * There is no batch route and this is not the place to invent one: the operations are the same
   * route the row calls, and the loop is what the merge queue already does for a batch of verdicts.
   * What matters is that it **reports what it wrote** — the archivist selected twenty tags and has to
   * learn that nineteen moved and which one did not.
   */
  const bulk = useMutation({
    mutationFn: async ({ ids, action }: { ids: number[]; action: BulkAction }) => {
      // One request per tag, so the failure of one is not the failure of the batch: it is caught
      // here and reported with the rest, which is the whole point of the bar saying what it wrote.
      const written: number[] = [];
      const failed: number[] = [];
      for (const tagId of ids) {
        try {
          await curateTag(tagId, {
            macro_category_id: action.kind === "category" ? action.categoryId : null,
            note: null,
          });
          written.push(tagId);
        } catch {
          failed.push(tagId);
        }
      }
      return { written, failed };
    },
    onSuccess: ({ written, failed }, variables) => {
      const action = variables.action;
      const destination =
        action.kind === "category"
          ? fill(messages.pages.tags.classify.destinationCategory, {
              name:
                drawers.find((category) => category.category_id === action.categoryId)?.name ??
                `#${action.categoryId}`,
            })
          : messages.pages.tags.classify.destinationNotSubject;
      setReport(
        fill(messages.pages.tags.classify.bulkReport, {
          count: formatCount(written.length),
          destination,
        }) +
          (failed.length > 0
            ? fill(messages.pages.tags.classify.bulkFailed, {
                count: formatCount(failed.length),
                ids: failed.join(", "),
              })
            : ""),
      );
      // What did not go through stays marked, so the retry is a click and not a re-selection.
      setSelected(failed);
    },
    /**
     * The list is refetched even when the loop stops halfway.
     *
     * The batch is one request per tag, so a failure on the seventh leaves six decisions already
     * written; without this the list would keep showing those six as pending, and the archivist
     * would read a write that happened as one that did not.
     */
    onSettled: invalidate,
  });

  const toggle = (tagId: number) =>
    setSelected((current) => (current.includes(tagId) ? current.filter((id) => id !== tagId) : [...current, tagId]));

  const pageIds = items.map((row) => row.tag_id);
  const allOnPage = pageIds.length > 0 && pageIds.every((id) => selected.includes(id));

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {CATALOG_STATES.map((value) => (
          <Button
            key={value}
            size="sm"
            variant={state === value ? "primary" : "secondary"}
            title={CATALOG_STATE_HINT[value]}
            // A different question is a different page: the fold resets the offset unless the caller
            // hands it one, which is exactly the rule the search-state gate pins.
            onClick={() => patch({ subject_state: value, termo: search.termo })}
          >
            {labelOf(CATALOG_STATE_LABEL, value)}
          </Button>
        ))}
      </div>

      <p className="max-w-3xl text-xs text-(--color-muted)">
        {CATALOG_STATE_HINT[state]}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <CatalogSearchBox value={search.termo} onSearch={(term) => patch({ termo: term })} />
        <Select
          className="w-56"
          value={search.cat ?? ""}
          onChange={(event) => patch({ cat: event.target.value ? Number(event.target.value) : undefined })}
        >
          <option value="">{messages.pages.tags.classify.allCategories}</option>
          {(categories.data ?? []).map((category) => (
            <option key={category.category_id} value={category.category_id}>
              {category.name}
              {category.is_active ? "" : messages.pages.tags.classify.retiredSuffix}
            </option>
          ))}
        </Select>
      </div>

      <p className="max-w-3xl text-xs text-(--color-muted)">
        <Trans
          text={messages.pages.tags.classify.notice}
          values={{
            everywhere: <strong>{messages.pages.tags.classify.everywhere}</strong>,
            notSubject: <strong>{messages.pages.tags.classify.notSubjectStrong}</strong>,
            place: (
              <Link to="/assuntos/grafias" className="font-medium underline underline-offset-2">
                {messages.screens.blockedSpellings.label}
              </Link>
            ),
          }}
        />
      </p>

      {curate.error ? <ErrorState error={curate.error} /> : null}
      {bulk.error ? <ErrorState error={bulk.error} /> : null}
      {report ? <Notice tone="ok">{report}</Notice> : null}

      {catalog.error ? <ErrorState error={catalog.error} /> : null}
      {catalog.isPending ? <Spinner label={messages.pages.tags.classify.readingCatalog} /> : null}

      {countsAreCurrent && total === 0 ? (
        <EmptyState
          title={messages.pages.tags.classify.emptyTitle}
          hint={
            state === "PENDING"
              ? messages.pages.tags.classify.emptyHintPending
              : messages.pages.tags.classify.emptyHintOther
          }
        />
      ) : null}

      {items.length > 0 ? (
        <Card>
          <CardHeader className="flex flex-wrap items-center justify-between gap-2 text-xs text-(--color-muted)">
            <span>
              {countsAreCurrent
                ? fill(messages.pages.tags.classify.countInState, { count: formatCount(total) })
                : messages.pages.tags.classify.reading}
              {search.termo ? fill(messages.pages.tags.classify.forTerm, { term: search.termo }) : ""}
            </span>
            <span className="flex items-center gap-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={allOnPage}
                  onChange={() => setSelected(allOnPage ? selected.filter((id) => !pageIds.includes(id)) : [...new Set([...selected, ...pageIds])])}
                />
                {messages.pages.tags.classify.selectPage}
              </label>
              {selected.length > 0 ? (
                <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
                  {fill(messages.pages.tags.classify.clearSelectionCount, {
                    count: formatCount(selected.length),
                  })}
                </Button>
              ) : null}
            </span>
          </CardHeader>
          <CardBody className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-(--color-line) text-xs text-(--color-muted)">
                <tr>
                  <th className="w-8 px-3 py-2" />
                  <th className="px-3 py-2 text-left font-medium">{messages.pages.tags.columns.tag}</th>
                  <th className="px-3 py-2 text-right font-medium">{messages.pages.tags.columns.documents}</th>
                  <th className="px-3 py-2 text-left font-medium">{messages.pages.tags.columns.state}</th>
                  <th className="px-3 py-2 text-left font-medium">{messages.pages.tags.columns.decide}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <CatalogRow
                    key={row.tag_id}
                    row={row}
                    drawers={drawers}
                    selected={selected.includes(row.tag_id)}
                    busy={curate.isPending}
                    onToggle={() => toggle(row.tag_id)}
                    onCurate={(categoryId) => curate.mutate({ tagId: row.tag_id, categoryId })}
                  />
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      ) : null}

      {countsAreCurrent && total > CATALOG_PAGE_SIZE ? (
        <div className="flex items-center justify-between text-sm">
          <Button size="sm" disabled={offset === 0} onClick={() => patch({ offset: Math.max(0, offset - CATALOG_PAGE_SIZE) })}>
            {messages.common.previous}
          </Button>
          <span className="text-xs text-(--color-muted)">
            {fill(messages.common.range, {
              from: formatCount(offset + 1),
              to: formatCount(Math.min(offset + CATALOG_PAGE_SIZE, total)),
              total: formatCount(total),
            })}
          </span>
          <Button
            size="sm"
            disabled={offset + CATALOG_PAGE_SIZE >= total}
            onClick={() => patch({ offset: offset + CATALOG_PAGE_SIZE })}
          >
            {messages.common.next}
          </Button>
        </div>
      ) : null}

      {/* The bar floats over the list so the decision is reachable from anywhere in it. */}
      {selected.length > 0 ? (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-40 flex justify-center">
          <div className="pointer-events-auto flex flex-wrap items-center gap-3 rounded-full bg-(--color-ink) px-4 py-2 text-sm text-white shadow-lg">
            <span>{fill(messages.pages.tags.classify.markedCount, { count: formatCount(selected.length) })}</span>
            <Select
              // ``text-(--color-ink)`` is not decoration: the bar is ``text-white`` and the control
              // is ``bg-white``, so without an explicit colour the placeholder renders white on
              // white — measured, and it was invisible until the screen was looked at.
              className="w-52 text-(--color-ink)"
              value=""
              disabled={bulk.isPending}
              onChange={(event) => {
                if (event.target.value) bulk.mutate({ ids: selected, action: { kind: "category", categoryId: Number(event.target.value) } });
              }}
            >
              <option value="">{messages.pages.tags.classify.moveToCategory}</option>
              {drawers.map((category) => (
                <option key={category.category_id} value={category.category_id}>
                  {category.name}
                  {category.is_active ? "" : messages.pages.tags.classify.retiredSuffix}
                </option>
              ))}
            </Select>
            <Button
              size="sm"
              variant="secondary"
              disabled={bulk.isPending}
              title={messages.pages.tags.classify.notSubjectTitle}
              onClick={() => bulk.mutate({ ids: selected, action: { kind: "not-subject" } })}
            >
              {messages.pages.tags.classify.notSubject}
            </Button>
            <button className="text-xs text-white/70 hover:text-white" onClick={() => setSelected([])}>
              {messages.pages.tags.clear}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** One row of the queue: the evidence, the state, and the two destinations. */
function CatalogRow({
  row,
  drawers,
  selected,
  busy,
  onToggle,
  onCurate,
}: {
  row: TagCatalogRow;
  drawers: MacroCategory[];
  selected: boolean;
  busy: boolean;
  onToggle: () => void;
  onCurate: (categoryId: number | null) => void;
}) {
  const messages = useCopy();
  const drawer = row.macro_category_id
    ? drawers.find((category) => category.category_id === row.macro_category_id)
    : undefined;

  return (
    <tr className="border-b border-(--color-line) last:border-b-0">
      <td className="px-3 py-1.5 align-top">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={fill(messages.pages.tags.row.markAria, { name: row.name })}
        />
      </td>
      <td className="px-3 py-1.5 align-top">
        <span className="flex min-w-0 flex-col">
          <span className="truncate">{row.name}</span>
          {row.ai_confidence_score !== null && row.ai_confidence_score !== undefined ? (
            <span
              className="text-xs tabular-nums text-(--color-muted)"
              title={messages.pages.tags.row.confidenceTitle}
            >
              {fill(messages.pages.tags.row.confidence, { score: row.ai_confidence_score.toFixed(2) })}
            </span>
          ) : null}
        </span>
      </td>
      <td className="px-3 py-1.5 text-right align-top tabular-nums">{formatCount(row.document_count)}</td>
      <td className="px-3 py-1.5 align-top">
        <span className="flex flex-wrap items-center gap-1">
          {row.macro_category_id ? (
            <Badge tone="accent">{drawer?.name ?? `#${row.macro_category_id}`}</Badge>
          ) : row.subject_excluded ? (
            <Badge tone="neutral" title={messages.pages.tags.row.excludedTitle}>
              {messages.pages.tags.classify.notSubject}
            </Badge>
          ) : (
            <Badge tone="warn" title={messages.pages.tags.row.noDecisionTitle}>
              {messages.pages.tags.row.noDecision}
            </Badge>
          )}
        </span>
      </td>
      <td className="px-3 py-1.5 align-top">
        <span className="flex flex-wrap items-center gap-2">
          <Select
            className="w-64"
            aria-label={fill(messages.pages.tags.row.categoryAria, { name: row.name })}
            value={row.macro_category_id ?? ""}
            disabled={busy}
            title={messages.pages.tags.row.categoryTitle}
            onChange={(event) => onCurate(event.target.value ? Number(event.target.value) : null)}
          >
            <option value="">{messages.pages.tags.row.noCategory}</option>
            {drawers.map((category) => (
              <option key={category.category_id} value={category.category_id}>
                {category.name}
                {category.is_active ? "" : messages.pages.tags.classify.retiredSuffix}
              </option>
            ))}
          </Select>
        </span>
      </td>
    </tr>
  );
}

/**
 * The queue's search box: it settles before it reaches the URL, which is what issues the request.
 *
 * The URL stays the source of truth, so a shared link, the back button or "limpar" wins over
 * whatever this box last held — and the box keeps its own value so typing never waits for a
 * navigation.
 */
function CatalogSearchBox({
  value,
  onSearch,
}: {
  value: string | undefined;
  onSearch: (term: string | undefined) => void;
}) {
  const messages = useCopy();
  const fromUrl = value ?? "";
  const [term, setTerm] = useState(fromUrl);
  const [seen, setSeen] = useState(fromUrl);
  const settled = useDebounced(term);

  if (fromUrl !== seen) {
    setSeen(fromUrl);
    setTerm(fromUrl);
  }

  useEffect(() => {
    // The debounce has to have caught up with the box before this can write: right after the URL
    // changes, ``settled`` still holds the term the box had a moment ago, and pushing that back
    // would rewrite the search the back button had just removed.
    if (settled.trim() !== term.trim()) return;
    const next = settled.trim();
    if (fromUrl === next) return;
    onSearch(next.length > 0 ? next : undefined);
  }, [settled, term, fromUrl, onSearch]);

  return (
    <Input
      className="max-w-xs"
      value={term}
      placeholder={messages.pages.tags.classify.searchPlaceholder}
      onChange={(event) => setTerm(event.target.value)}
    />
  );
}

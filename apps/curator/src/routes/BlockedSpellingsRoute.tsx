import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  banStopwords,
  previewStopwordPurge,
  purgeStopwords,
  setStopwordMatch,
  unbanStopwords,
  undoStopwordPurge,
  type StopwordMatch,
  type StopwordPurgePreview,
  type StopwordsScope,
} from "@/api/client";
import { MERGE_LOG_PAGE_SIZE, queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageBody } from "@/components/layout/PageBody";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Hint } from "@/components/ui/Hint";
import { Input, Select } from "@/components/ui/Input";
import { LedgerList } from "@/components/ui/LedgerList";
import { Notice } from "@/components/ui/Notice";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { Trans } from "@/i18n/trans";
import { ACTION } from "@/lib/copy";
import { formatCount, formatDateTime } from "@/lib/format";
import { asEnum } from "@/lib/search";
import {
  STOPWORD_MATCH_HINT,
  STOPWORD_MATCH_LABEL,
  STOPWORD_SCOPE_HINT,
  STOPWORD_SCOPE_LABEL,
  STOPWORD_SOURCE_HINT,
  STOPWORD_SOURCE_LABEL,
  labelOf,
} from "@/lib/taxonomy";
import { useDebounced } from "@/lib/useDebounced";

const routeApi = getRouteApi("/assuntos/grafias");

/** The axis a ban is scoped to, in the order the screen offers it. */
const SCOPE_VALUES: StopwordsScope[] = ["TAG", "ENTITY", "ALL"];
/** The two ways a ban matches, in the order the screen offers them (#160). */
const MATCH_VALUES: StopwordMatch[] = ["TOKEN", "EXACT"];

export type BlockedSpellingsSearch = { escopo?: StopwordsScope };

export function validateBlockedSpellingsSearch(search: Record<string, unknown>): BlockedSpellingsSearch {
  return { escopo: asEnum(search.escopo, SCOPE_VALUES) };
}

/** "pessoas, vista aérea" → ["pessoas", "vista aérea"]. */
function splitWords(text: string): string[] {
  return text
    .split(/[,\n;]/)
    .map((word) => word.trim())
    .filter((word) => word.length > 0);
}

/**
 * The spellings a ban keeps out of the vocabulary, and the one write that deletes a tag.
 *
 * This was the fourth tab of `/assuntos/tags` until #232, and the move is the whole point of that
 * issue: the page described relevance, duplicates and merge, and never said that its `Termos
 * Bloqueados` tab held the only destructive write of the taxonomy. Two clicks under a description
 * that denied it existed, and next to a screen whose sentences read like synonyms of its own.
 *
 * The screen keeps three things apart, and each one is stated where it matters: banning a spelling
 * **deletes nothing**; the exclusion of the tags with those names **does**, and keeps a ledger that
 * restores the tag, its links and its spellings (but never unbans the term); and the scope decides
 * which of those is possible — a term banned from the NER axis never reaches the subject purge.
 *
 * The copy that keeps it apart from `/assuntos/excecoes` is the notice and the header's link, and
 * the direction that matters is the one stated: an archivist lands here expecting the classifier to
 * stop, and it does not.
 */
export function BlockedSpellingsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const messages = useCopy();

  const patch = (changes: Partial<BlockedSpellingsSearch>) =>
    navigate({ to: "/assuntos/grafias", search: { ...search, ...changes } });

  return (
    <>
      <PageHeader
        screen="blockedSpellings"
        actions={
          <Link to="/assuntos/excecoes">
            <Button size="sm">{messages.screens.subjectExclusions.label}</Button>
          </Link>
        }
      />
      <PageBody>
        <BlockedSpellingsBody search={search} patch={patch} />
      </PageBody>
    </>
  );
}

function BlockedSpellingsBody({
  search,
  patch,
}: {
  search: BlockedSpellingsSearch;
  patch: (changes: Partial<BlockedSpellingsSearch>) => void;
}) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [draftScope, setDraftScope] = useState<StopwordsScope>("TAG");
  /** Only the extraction axis reads it: a TAG ban never reaches the NER filter (#160). */
  const [draftMatch, setDraftMatch] = useState<StopwordMatch>("TOKEN");
  const [preview, setPreview] = useState<StopwordPurgePreview | null>(null);
  const [purged, setPurged] = useState<number | null>(null);
  const [purgeIds, setPurgeIds] = useState<number[]>([]);
  const [logTerm, setLogTerm] = useState("");
  const [logLimit, setLogLimit] = useState(MERGE_LOG_PAGE_SIZE);
  const settledLogTerm = useDebounced(logTerm);

  const stopwords = useQuery(queries.stopwords(search.escopo));
  const log = useQuery(queries.stopwordPurgeLog(logLimit, settledLogTerm.trim() || undefined));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "stopwords"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "stopword-purge-log"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const ban = useMutation({
    mutationFn: () => banStopwords({ words: splitWords(draft), scope: draftScope, match_mode: draftMatch }),
    onSuccess: () => {
      setDraft("");
      invalidate();
    },
  });

  const setMatch = useMutation({
    mutationFn: (input: { word: string; match_mode: StopwordMatch }) =>
      setStopwordMatch({ words: [input.word], match_mode: input.match_mode }),
    onSuccess: invalidate,
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
      setPurgeIds([]);
    },
  });

  const purge = useMutation({
    mutationFn: purgeStopwords,
    onSuccess: (data) => {
      setPurged(data.tags_deleted);
      setPurgeIds(data.purge_ids ?? []);
      setPreview(null);
      invalidate();
    },
  });

  const revertPurge = useMutation({
    mutationFn: (purgeId: number) => undoStopwordPurge(purgeId),
    onSuccess: () => {
      setPurgeIds([]);
      invalidate();
    },
  });

  const words = stopwords.data ?? [];
  const byScope = (scope: StopwordsScope) => words.filter((item) => item.scope === scope);

  return (
    <div className="grid gap-4">
      {/*
        The one sentence that keeps this screen apart from `Não é assunto`, and it is on this screen
        because this is the one readers arrive on expecting the other: a ban looks like a verdict
        about meaning and is not. The two names it needs are supplied as markup, so the link is part
        of the sentence and the card below is named here and in its own header from one string.
      */}
      <Notice tone="neutral" className="max-w-3xl">
        <Trans
          text={messages.spellings.notice}
          values={{
            verdict: <Link to="/assuntos/excecoes">{messages.screens.subjectExclusions.label}</Link>,
            purge: <strong>{messages.spellings.purgeCard}</strong>,
          }}
        />
      </Notice>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={search.escopo ? "secondary" : "primary"} onClick={() => patch({ escopo: undefined })}>
          {fill(messages.pages.blockedSpellings.allSpellings, { count: formatCount(words.length) })}
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

      <Card>
        <CardHeader className="text-sm font-semibold">{messages.pages.blockedSpellings.banCard}</CardHeader>
        <CardBody className="grid gap-2">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex-1">
              <span className="mb-1 block text-xs font-medium text-(--color-muted)">
                {messages.pages.blockedSpellings.banField}
              </span>
              <Input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={messages.pages.blockedSpellings.banPlaceholder}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && splitWords(draft).length > 0) ban.mutate();
                }}
              />
            </label>
            <label className="w-56">
              <span className="mb-1 block text-xs font-medium text-(--color-muted)">
                {messages.pages.blockedSpellings.scopeField}
              </span>
              <Select value={draftScope} onChange={(event) => setDraftScope(event.target.value as StopwordsScope)}>
                {SCOPE_VALUES.map((scope) => (
                  <option key={scope} value={scope}>
                    {labelOf(STOPWORD_SCOPE_LABEL, scope)}
                  </option>
                ))}
              </Select>
            </label>
            {/*
              Only the extraction axis reads the mode: a TAG ban never reaches the NER filter, and
              offering the choice there would imply it does.
            */}
            {draftScope !== "TAG" ? (
              <label className="w-64">
                <span className="mb-1 block text-xs font-medium text-(--color-muted)">
                  {messages.pages.blockedSpellings.matchField}
                </span>
                <Select value={draftMatch} onChange={(event) => setDraftMatch(event.target.value as StopwordMatch)}>
                  {MATCH_VALUES.map((mode) => (
                    <option key={mode} value={mode}>
                      {labelOf(STOPWORD_MATCH_LABEL, mode)}
                    </option>
                  ))}
                </Select>
              </label>
            ) : null}
            <Button
              variant="primary"
              disabled={splitWords(draft).length === 0 || ban.isPending}
              onClick={() => ban.mutate()}
            >
              {ban.isPending ? ACTION.ban.pending : ACTION.ban.label}
            </Button>
          </div>
          <p className="text-xs text-(--color-muted)">
            {STOPWORD_SCOPE_HINT[draftScope]}
            {draftScope !== "TAG" ? ` ${STOPWORD_MATCH_HINT[draftMatch]}` : ""}
          </p>
          {ban.error ? <ErrorState error={ban.error} /> : null}
          {unban.error ? <ErrorState error={unban.error} /> : null}
        </CardBody>
      </Card>

      {stopwords.error ? <ErrorState error={stopwords.error} /> : null}
      {stopwords.isPending ? <Spinner label={messages.pages.blockedSpellings.reading} /> : null}

      {stopwords.data && words.length === 0 ? (
        <EmptyState
          title={messages.pages.blockedSpellings.emptyTitle}
          hint={messages.pages.blockedSpellings.emptyHint}
        />
      ) : null}

      {words.length > 0 ? (
        <Card>
          <CardHeader className="text-sm font-semibold">{messages.screens.blockedSpellings.label}</CardHeader>
          <CardBody>
            {/*
              A searchable ledger and not a flat column: 200 blocked spellings is already past the
              point where scrolling to find one is reasonable, and the list only grows.
            */}
            <LedgerList
              items={words}
              keyOf={(item) => item.word}
              termOf={(item) => [
                item.word,
                labelOf(STOPWORD_SCOPE_LABEL, item.scope),
                labelOf(STOPWORD_SOURCE_LABEL, item.source),
              ]}
              searchPlaceholder={messages.pages.blockedSpellings.searchPlaceholder}
              nounSingular={messages.pages.blockedSpellings.nounSingular}
              nounPlural={messages.pages.blockedSpellings.nounPlural}
              emptyTitle={messages.pages.blockedSpellings.emptyTitle}
              emptyHint={messages.pages.blockedSpellings.emptyHint}
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
                    {item.source !== "HUMAN" ? (
                      <Badge tone="neutral" title={STOPWORD_SOURCE_HINT[item.source]}>
                        {labelOf(STOPWORD_SOURCE_LABEL, item.source)}
                      </Badge>
                    ) : null}
                    {/*
                      The mode is a control, not a badge: it decides whether the ban swallows the
                      names that contain the word, and changing it is one act on its own (#160).
                      A TAG ban never reaches the NER filter, so it carries no mode here.
                    */}
                    {item.scope !== "TAG" ? (
                      <Select
                        className="h-7 w-64 text-xs"
                        value={item.match_mode}
                        title={STOPWORD_MATCH_HINT[item.match_mode]}
                        disabled={setMatch.isPending}
                        onChange={(event) =>
                          setMatch.mutate({
                            word: item.word,
                            match_mode: event.target.value as StopwordMatch,
                          })
                        }
                      >
                        {MATCH_VALUES.map((mode) => (
                          <option key={mode} value={mode}>
                            {labelOf(STOPWORD_MATCH_LABEL, mode)}
                          </option>
                        ))}
                      </Select>
                    ) : null}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {/*
                      A ban whose source is `EXCLUSION` was planted by a verdict on the other screen,
                      and that is the only way to reach the decision that owns it: the badge says
                      where it came from, and this says where to go. It carries the term, so the
                      ledger does not open on two hundred rows to find one.
                    */}
                    {item.source === "EXCLUSION" ? (
                      <Link
                        to="/assuntos/excecoes"
                        search={{ termo: item.word }}
                        title={STOPWORD_SOURCE_HINT.EXCLUSION}
                        className="text-xs text-(--color-muted) underline-offset-2 hover:text-(--color-ink) hover:underline"
                      >
                        {fill(messages.pages.blockedSpellings.seeIn, {
                          place: messages.screens.subjectExclusions.label,
                        })}
                      </Link>
                    ) : null}
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={unban.isPending}
                      onClick={() => unban.mutate(item.word)}
                    >
                      {ACTION.unban.label}
                    </Button>
                  </span>
                </div>
              )}
            />
          </CardBody>
        </Card>
      ) : null}

      <Card className="ring-(--color-danger)/30">
        <CardHeader className="text-sm font-semibold text-(--color-danger)">{messages.spellings.purgeCard}</CardHeader>
        <CardBody className="grid gap-3">
          <p className="text-xs text-(--color-muted)">{messages.pages.blockedSpellings.purge.body}</p>

          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={dryRun.isPending || purge.isPending} onClick={() => dryRun.mutate()}>
              {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
            </Button>
            <Button
              variant="danger"
              disabled={!preview || preview.total_tags === 0 || purge.isPending}
              title={preview ? undefined : messages.pages.blockedSpellings.purge.previewRequired}
              onClick={() => purge.mutate()}
            >
              {purge.isPending
                ? ACTION.exclude.pending
                : preview
                  ? fill(messages.pages.blockedSpellings.purge.excludeCount, {
                      count: formatCount(preview.total_tags),
                    })
                  : messages.pages.blockedSpellings.purge.excludeFirst}
            </Button>
          </div>

          {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
          {purge.error ? <ErrorState error={purge.error} /> : null}

          {preview ? (
            <Notice tone="danger" as="div" className="grid gap-2">
              <p>
                <Trans
                  text={messages.pages.blockedSpellings.purge.previewLead}
                  values={{
                    tags: (
                      <strong>
                        {fill(messages.pages.blockedSpellings.purge.previewTags, {
                          count: formatCount(preview.total_tags),
                        })}
                      </strong>
                    ),
                    documents: (
                      <strong>
                        {fill(messages.pages.blockedSpellings.purge.previewDocuments, {
                          count: formatCount(preview.total_documents),
                        })}
                      </strong>
                    ),
                  }}
                />
              </p>
              {(preview.stopwords ?? []).length > 0 ? (
                <p className="text-(--color-muted)">
                  {messages.pages.blockedSpellings.purge.reached}{" "}
                  <code>{(preview.stopwords ?? []).join(", ")}</code>
                </p>
              ) : null}
              {preview.total_tags === 0 ? (
                <p className="text-(--color-muted)">{messages.pages.blockedSpellings.purge.nothingToExclude}</p>
              ) : (
                <ul className="max-h-64 overflow-y-auto">
                  {(preview.tags ?? []).map((tag) => (
                    <li key={tag.tag_id} className="flex items-center justify-between gap-3 py-0.5">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="truncate">{tag.name}</span>
                        {tag.source !== "HUMAN" ? (
                          <Badge tone="neutral" title={STOPWORD_SOURCE_HINT[tag.source]}>
                            {labelOf(STOPWORD_SOURCE_LABEL, tag.source)}
                          </Badge>
                        ) : null}
                      </span>
                      <span className="shrink-0 tabular-nums text-(--color-muted)">
                        {fill(messages.pages.blockedSpellings.purge.docCount, {
                          count: formatCount(tag.document_count),
                        })}
                        {tag.macro_category_name ? ` · ${tag.macro_category_name}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Notice>
          ) : null}

          {purged !== null ? (
            <Notice tone="ok" as="div" className="grid gap-2">
              <p>
                {fill(messages.pages.blockedSpellings.purge.purged, { count: formatCount(purged) })}
              </p>
              {purgeIds.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={revertPurge.isPending}
                    title={messages.pages.blockedSpellings.purge.undoTitle}
                    onClick={() => {
                      const [first] = purgeIds;
                      if (first !== undefined) revertPurge.mutate(first);
                    }}
                  >
                    {messages.pages.blockedSpellings.purge.undo}
                  </Button>
                  <span className="text-(--color-muted)">
                    {messages.pages.blockedSpellings.purge.entries} <code>{purgeIds.join(", ")}</code>
                  </span>
                </div>
              ) : null}
            </Notice>
          ) : null}
          {revertPurge.error ? <ErrorState error={revertPurge.error} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="text-sm font-semibold">
          {messages.pages.blockedSpellings.log.title}
          <Hint
            label={messages.pages.blockedSpellings.log.title}
            className="text-xs text-(--color-muted)"
          >
            <Trans
              text={messages.pages.blockedSpellings.log.hint}
              values={{ strong: <strong>{messages.pages.blockedSpellings.log.hintStrong}</strong> }}
            />
          </Hint>
        </CardHeader>
        <CardBody className="grid gap-2">
          {/*
            This search is server-side: the ledger only grows, and a box that filtered the loaded
            page would say "não está aqui" for an exclusion that happened.
          */}
          <Input
            className="max-w-xs"
            value={logTerm}
            placeholder={messages.pages.blockedSpellings.log.searchPlaceholder}
            onChange={(event) => setLogTerm(event.target.value)}
          />
          {log.isPending ? <Spinner label={messages.pages.blockedSpellings.log.reading} /> : null}
          {log.error ? <ErrorState error={log.error} /> : null}
          {log.data && (log.data.items ?? []).length === 0 ? (
            <EmptyState
              title={
                logTerm.trim()
                  ? fill(messages.pages.blockedSpellings.log.emptyTerm, { term: logTerm.trim() })
                  : messages.pages.blockedSpellings.log.empty
              }
              hint={
                logTerm.trim()
                  ? messages.pages.blockedSpellings.log.emptyTermHint
                  : messages.pages.blockedSpellings.log.emptyHint
              }
            />
          ) : null}
          <ul className="divide-y divide-(--color-line) text-xs">
            {(log.data?.items ?? []).map((entry) => (
              <li key={entry.purge_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="min-w-0">
                  <span className="font-medium">{entry.purged_name}</span>
                  <span className="text-(--color-muted)">
                    {" "}
                    {fill(messages.pages.blockedSpellings.log.row, {
                      documents: formatCount(entry.document_count),
                      date: formatDateTime(entry.changed_at),
                    })}
                    {entry.changed_by
                      ? ` ${fill(messages.pages.blockedSpellings.log.by, { name: entry.changed_by })}`
                      : ""}
                    {entry.macro_category_name ? ` · ${entry.macro_category_name}` : ""}
                  </span>
                </span>
                {entry.undone_at ? (
                  <Badge tone="neutral">
                    {fill(messages.pages.blockedSpellings.log.restored, {
                      date: formatDateTime(entry.undone_at),
                    })}
                  </Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={revertPurge.isPending}
                    title={messages.pages.blockedSpellings.log.undoTitle}
                    onClick={() => revertPurge.mutate(entry.purge_id)}
                  >
                    {messages.pages.blockedSpellings.log.undo}
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {/*
            The footer appears whenever there is something to say: more rows below, or a search that
            matched — the same rule the merge ledger follows.
          */}
          {log.data && (log.data.total > (log.data.items ?? []).length || settledLogTerm.trim()) ? (
            <div className="flex items-center gap-2">
              {log.data.total > (log.data.items ?? []).length ? (
                <Button size="sm" variant="ghost" onClick={() => setLogLimit((current) => current + MERGE_LOG_PAGE_SIZE)}>
                  {messages.pages.blockedSpellings.log.seeMore}
                </Button>
              ) : null}
              <span className="text-xs text-(--color-muted)">
                {fill(
                  settledLogTerm.trim()
                    ? messages.pages.blockedSpellings.log.showingFiltered
                    : messages.pages.blockedSpellings.log.showing,
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

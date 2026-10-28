import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  previewConflictResolution,
  resolveConflict,
  resolveConflictBatch,
  undoConflictResolution,
  type ConflictBatchResult,
  type ConflictPairKindFilter,
  type ConflictResolutionPlan,
  type ConflictWinner,
  type EntityType,
} from "@/api/client";
import { CONFLICTS_BATCH_LIMIT, CONFLICTS_PAGE_SIZE, queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Hint } from "@/components/ui/Hint";
import { Input } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { PageBody } from "@/components/layout/PageBody";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { Trans } from "@/i18n/trans";
import { ACTION } from "@/lib/copy";
import { CONFLICT_WINNER_HINT, CONFLICT_WINNER_LABEL, CONFLICT_WINNER_TONE, ENTITY_TYPE_HINT, ENTITY_TYPE_LABEL } from "@/lib/entities";
import { formatCount, formatDateTime } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";
import { asNumber } from "@/lib/search";
import { routeMessage } from "@/lib/messages";

const routeApi = getRouteApi("/entidades/conflitos");

export type ConflictsSearch = {
  limiar?: number;
  ver?: ConflictView;
  tipo?: ConflictPairKindFilter;
  categoria?: EntityType;
  pagina?: number;
};

/** The three reads this screen makes: the live pairs, the judge's verdicts, and the ledger. */
export type ConflictView = "pendentes" | "decididos" | "resolucoes";

/** The three reads, in the order the tabs offer them. */
const VIEW_KEYS: ConflictView[] = ["pendentes", "decididos", "resolucoes"];

/** The populations of the live scan, in the order the filter buttons offer them. */
const PAIR_KIND_KEYS: ConflictPairKindFilter[] = ["near_duplicate", "exact_name", "all"];

/** The categories of named entity, as the filter and the batch name them: "a street is an entity". */
const ENTITY_KIND_KEYS = ["all", "LOC", "PER", "ORG"] as const;

export function validateConflictsSearch(search: Record<string, unknown>): ConflictsSearch {
  const limiar = asNumber(search.limiar);
  const pagina = asNumber(search.pagina);
  const ver = search.ver;
  const tipo = search.tipo;
  const categoria = search.categoria;
  return {
    limiar: limiar !== undefined && limiar > 0 && limiar <= 1 ? limiar : undefined,
    ver: ver === "decididos" || ver === "resolucoes" ? ver : undefined,
    tipo: tipo === "exact_name" || tipo === "all" || tipo === "near_duplicate" ? tipo : undefined,
    categoria: categoria === "ORG" || categoria === "PER" || categoria === "LOC" ? categoria : undefined,
    pagina: pagina !== undefined && pagina > 0 ? pagina : undefined,
  };
}

/**
 * The tag x entity collision: "is this spelling a subject or a proper name?".
 *
 * The decision is not symmetric, and that is the whole lesson of the screen: the two verdicts are
 * stored in **different places**, on purpose. Entity wins -> the tag's name is banned from the
 * subject axis (``DomainStopwords``, scope ``TAG``); tag wins -> the term is recorded as a NER
 * exclusion carrying the tag that justifies it. Collapsing the two would let a NER veto make the
 * subject purge delete a tag the curator kept.
 *
 * Three reads, because they answer three different questions — and reading only the first is what
 * hid the judge's work:
 *
 * * **pendentes** — the live trigram scan, annotated with the judge's verdict where there is one and
 *   separated by ``pair_kind``: 5 050 identical names and 122 different spellings are not the same
 *   question, and mixed together neither is visible;
 * * **decididos** — the review queue. An auto-resolution deletes the losing row, so 84 of the 88
 *   real decisions cannot appear in the live scan at all;
 * * **resolucoes** — the ledger, with the undo. Until it existed, transferring the documents and
 *   deleting a row were irreversible, for the judge and for the archivist alike.
 */
export function ConflictsRoute() {
  const messages = useCopy();
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const threshold = search.limiar ?? 0.85;
  const view = search.ver ?? "pendentes";
  const pairKind = search.tipo ?? "near_duplicate";
  const entityType = search.categoria;
  const page = search.pagina ?? 0;

  /**
   * The threshold is typed before it is applied.
   *
   * The URL stays the source of truth, but a live ``onChange`` would run the whole trigram join once
   * per keystroke — "0.75" would be three scans of two vocabularies, and the first two answer a
   * question nobody asked. It is applied on blur or Enter instead.
   */
  const [draft, setDraft] = useState(String(threshold));
  const [seen, setSeen] = useState(threshold);
  if (seen !== threshold) {
    setSeen(threshold);
    setDraft(String(threshold));
  }

  /** The pair whose impact is being shown. The write only happens after this panel is read. */
  const [preview, setPreview] = useState<ConflictResolutionPlan | null>(null);
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  /**
   * The categorical decision, and the report it leaves behind.
   *
   * The panel is opened by hand and states the selection before anything is written: the count comes
   * from the same read the list is drawn from, so "36 pairs" cannot mean one thing in the button and
   * another in the write. The response's ``remaining`` is that same read, taken again.
   */
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchNote, setBatchNote] = useState("");
  const [batchResult, setBatchResult] = useState<ConflictBatchResult | null>(null);

  const conflicts = useQuery(queries.crossDomainConflicts(threshold, pairKind, entityType, page));
  const judged = useQuery({ ...queries.judgedConflicts(page), enabled: view === "decididos" });
  const ledger = useQuery({ ...queries.conflictResolutions(page), enabled: view === "resolucoes" });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "conflicts"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "stopwords"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "ner-exclusions"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "entities"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const ask = useMutation({
    mutationFn: (pair: { tag_id: number; entity_id: number }) => previewConflictResolution(pair),
    onSuccess: (plan) => {
      setPreview(plan);
      setFeedback(null);
    },
  });

  const resolve = useMutation({
    mutationFn: (body: { tag_id: number; entity_id: number; winner: ConflictWinner }) =>
      resolveConflict({ ...body, note: note || null }),
    onSuccess: (response) => {
      setFeedback(routeMessage(response));
      setPreview(null);
      setNote("");
      invalidate();
    },
  });

  const undo = useMutation({
    mutationFn: (resolutionId: number) => undoConflictResolution(resolutionId),
    onSuccess: (response) => {
      setFeedback(routeMessage(response));
      invalidate();
    },
  });

  /**
   * One verdict, the whole on-screen selection, one ledger row per pair.
   *
   * ``pair_kind`` and ``entity_type`` travel exactly as the list is filtered — what the archivist
   * sees is what the batch writes — and ``limit`` bounds one click so a large population is settled
   * in reviewed chunks instead of one anonymous sweep.
   */
  const resolveBatch = useMutation({
    mutationFn: (winner: ConflictWinner) =>
      resolveConflictBatch({
        winner,
        pair_kind: pairKind,
        entity_type: entityType ?? null,
        threshold,
        limit: CONFLICTS_BATCH_LIMIT,
        note: batchNote || null,
      }),
    onSuccess: (response) => {
      setFeedback(routeMessage(response));
      setBatchResult(response.data);
      setBatchOpen(false);
      setBatchNote("");
      invalidate();
    },
  });

  const applyThreshold = () => {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 1) {
      setDraft(String(threshold));
      return;
    }
    navigate({ to: "/entidades/conflitos", search: { ...search, limiar: parsed, pagina: undefined } });
  };

  const goTo = (next: ConflictsSearch) =>
    navigate({ to: "/entidades/conflitos", search: { ...search, ...next, pagina: undefined } });

  const active = view === "decididos" ? judged : view === "resolucoes" ? ledger : conflicts;
  const total =
    view === "decididos"
      ? (judged.data?.total ?? 0)
      : view === "resolucoes"
        ? (ledger.data?.total ?? 0)
        : (conflicts.data?.total ?? 0);
  const lastPage = Math.max(1, Math.ceil(total / CONFLICTS_PAGE_SIZE));

  const entityKinds: { key: "all" | EntityType; label: string; hint: string }[] = ENTITY_KIND_KEYS.map((key) =>
    key === "all"
      ? { key, ...messages.pages.conflicts.entityKind.all }
      : { key, label: labelOf(ENTITY_TYPE_LABEL, key), hint: labelOf(ENTITY_TYPE_HINT, key) },
  );

  return (
    <>
      <PageHeader
        screen="conflicts"
        pending={view === "pendentes" ? conflicts.isPending : view === "decididos" ? judged.isPending : ledger.isPending}
        status={
          view === "pendentes" && conflicts.data
            ? fill(messages.pages.conflicts.status.pairs, {
                count: formatCount(conflicts.data.total),
                threshold: threshold.toFixed(2),
              })
            : view === "decididos" && judged.data
              ? fill(messages.pages.conflicts.status.judged, {
                  judged: formatCount(judged.data.total),
                  decidable: formatCount(judged.data.still_applicable),
                })
              : view === "resolucoes" && ledger.data
                ? fill(messages.pages.conflicts.status.ledger, { count: formatCount(ledger.data.total) })
                : undefined
        }
      />

      {/* The three reads are tabs, not filters: they are different questions about different data. */}
      <div className="px-6 pt-4">
        <Tabs
          items={VIEW_KEYS.map((key) => ({ id: key, ...messages.pages.conflicts.view[key] }))}
          active={view}
          onChange={(id) => {
            const next = VIEW_KEYS.find((item) => item === id);
            goTo({ ver: next === "pendentes" ? undefined : next });
          }}
        />
      </div>

      <PageBody>
        <Disclosure
          toggleLabel={messages.pages.conflicts.storage.toggle}
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">{messages.pages.conflicts.storage.toggle}</span>
              <span className="text-xs text-(--color-muted)">
                {fill(messages.pages.conflicts.storage.summary, {
                  tag: labelOf(CONFLICT_WINNER_HINT, "TAG"),
                  entity: labelOf(CONFLICT_WINNER_HINT, "ENTITY"),
                })}
              </span>
            </div>
          }
        >
          <p className="text-xs text-(--color-accent)">
            <Trans
              text={messages.pages.conflicts.storage.body}
              values={{ places: <strong>{messages.pages.conflicts.storage.places}</strong> }}
            />
          </p>
        </Disclosure>

        {view === "pendentes" ? (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <Field
                label={messages.pages.conflicts.threshold.label}
                info={
                  <Hint label={messages.pages.conflicts.threshold.hintLabel} align="start">
                    {messages.pages.conflicts.threshold.hint}
                  </Hint>
                }
              >
                <Input
                  type="number"
                  min={0.5}
                  max={1}
                  step={0.05}
                  value={draft}
                  className="w-28"
                  onChange={(event) => setDraft(event.target.value)}
                  onBlur={applyThreshold}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") applyThreshold();
                  }}
                />
              </Field>
              {conflicts.data ? (
                <p className="text-xs text-(--color-muted)">
                  {fill(messages.pages.conflicts.counts, {
                    near: formatCount(conflicts.data.near_duplicate_count),
                    exact: formatCount(conflicts.data.exact_name_count),
                    judged: formatCount(conflicts.data.judged_count),
                  })}
                </p>
              ) : null}
            </div>

            {/*
              The population filter is the whole reason this list is usable. Measured on the real
              collection: 5 408 pairs, of which 5 050 are the same spelling on both axes and 122 are
              the same word written differently. "Which one do I want to see?" is the first question,
              not a refinement of the list.
            */}
            <div className="flex flex-wrap gap-2">
              {PAIR_KIND_KEYS.map((key) => (
                <Button
                  key={key}
                  size="sm"
                  variant={pairKind === key ? "primary" : "ghost"}
                  title={messages.pages.conflicts.pairKind[key].hint}
                  onClick={() => goTo({ tipo: key === "near_duplicate" ? undefined : key })}
                >
                  {messages.pages.conflicts.pairKind[key].label}
                </Button>
              ))}
            </div>

            {/*
              The category narrows the structural population to the set a categorical decision can
              name: "a street is an entity" is about the LOC collisions, not about one pair at a time.
              It lives in the URL because it is also the selection the batch writes.
            */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-(--color-muted)">{messages.pages.conflicts.categoryLabel}</span>
              {entityKinds.map((kind) => (
                <Button
                  key={kind.key}
                  size="sm"
                  variant={(entityType ?? "all") === kind.key ? "primary" : "ghost"}
                  title={kind.hint}
                  onClick={() => goTo({ categoria: kind.key === "all" ? undefined : kind.key })}
                >
                  {kind.label}
                </Button>
              ))}
            </div>

            {conflicts.data && conflicts.data.total > 0 ? (
              <Card>
                <CardBody className="grid gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold">{messages.pages.conflicts.batch.title}</span>
                    <Badge tone="neutral">
                      {fill(messages.pages.conflicts.batch.badge, {
                        count: formatCount(conflicts.data.total),
                        kind: messages.pages.conflicts.pairKind[pairKind].label,
                        category: entityType
                          ? fill(messages.pages.conflicts.batch.badgeCategory, {
                              category: labelOf(ENTITY_TYPE_LABEL, entityType),
                            })
                          : "",
                      })}
                    </Badge>
                  </div>
                  <p className="text-xs text-(--color-muted)">
                    {fill(messages.pages.conflicts.batch.body, { limit: formatCount(CONFLICTS_BATCH_LIMIT) })}
                  </p>
                  {batchOpen ? (
                    <div className="grid gap-2">
                      <Field label={messages.pages.conflicts.noteField}>
                        <Input value={batchNote} onChange={(event) => setBatchNote(event.target.value)} />
                      </Field>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="primary"
                          disabled={resolveBatch.isPending}
                          title={CONFLICT_WINNER_HINT.TAG}
                          onClick={() => resolveBatch.mutate("TAG")}
                        >
                          {fill(messages.pages.conflicts.batch.apply, {
                            verb: ACTION.apply.label,
                            winner: labelOf(CONFLICT_WINNER_LABEL, "TAG"),
                          })}
                        </Button>
                        <Button
                          variant="primary"
                          disabled={resolveBatch.isPending}
                          title={CONFLICT_WINNER_HINT.ENTITY}
                          onClick={() => resolveBatch.mutate("ENTITY")}
                        >
                          {fill(messages.pages.conflicts.batch.apply, {
                            verb: ACTION.apply.label,
                            winner: labelOf(CONFLICT_WINNER_LABEL, "ENTITY"),
                          })}
                        </Button>
                        <Button
                          variant="ghost"
                          disabled={resolveBatch.isPending}
                          onClick={() => setBatchOpen(false)}
                        >
                          {ACTION.cancel.label}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        title={messages.pages.conflicts.batch.openTitle}
                        onClick={() => setBatchOpen(true)}
                      >
                        {messages.pages.conflicts.batch.open}
                      </Button>
                    </div>
                  )}
                </CardBody>
              </Card>
            ) : null}
          </>
        ) : null}

        {feedback ? (
          <Notice tone="ok">
            {feedback}
          </Notice>
        ) : null}
        {batchResult ? <BatchReport result={batchResult} /> : null}
        {active.error ? <ErrorState error={active.error} /> : null}
        {active.isPending ? <Spinner label={messages.pages.conflicts.reading} /> : null}
        {resolve.error ? <ErrorState error={resolve.error} /> : null}
        {resolveBatch.error ? <ErrorState error={resolveBatch.error} /> : null}
        {undo.error ? <ErrorState error={undo.error} /> : null}
        {ask.error ? <ErrorState error={ask.error} /> : null}

        {preview ? (
          <PreviewPanel
            plan={preview}
            note={note}
            pending={resolve.isPending}
            onNote={setNote}
            onCancel={() => setPreview(null)}
            onConfirm={(winner) => resolve.mutate({ tag_id: preview.tag_id, entity_id: preview.entity_id, winner })}
          />
        ) : null}

        {view === "pendentes" ? (
          <>
            {conflicts.data && (conflicts.data.items ?? []).length === 0 && !preview ? (
              <EmptyState
                title={messages.pages.conflicts.empty.title}
                hint={messages.pages.conflicts.empty.hint}
              />
            ) : null}
            <ul className="grid gap-2">
              {(conflicts.data?.items ?? []).map((row) => (
                <li key={`${row.tag_id}-${row.entity_id}`}>
                  <Card>
                    <CardBody className="grid gap-2">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="flex min-w-0 items-center gap-2">
                          <Badge tone="accent">{messages.pages.conflicts.pair.subject}</Badge>
                          <span className="truncate text-sm font-medium">{row.tag_name}</span>
                          <code className="text-[10px] text-(--color-muted)">#{row.tag_id}</code>
                        </span>
                        <span className="text-(--color-muted)">≈ {row.similarity.toFixed(3)} ≈</span>
                        <span className="flex min-w-0 items-center gap-2">
                          <Badge tone="ok">{labelOf(ENTITY_TYPE_LABEL, row.entity_type)}</Badge>
                          <span className="truncate text-sm font-medium">{row.entity_name}</span>
                          <code className="text-[10px] text-(--color-muted)">#{row.entity_id}</code>
                        </span>
                        <Badge tone={row.pair_kind === "EXACT_NAME" ? "neutral" : "warn"}>
                          {row.pair_kind === "EXACT_NAME"
                            ? messages.pages.conflicts.pair.sameSpelling
                            : messages.pages.conflicts.pair.similarSpelling}
                        </Badge>
                        {row.judge_winner ? (
                          <Badge tone={CONFLICT_WINNER_TONE[row.judge_winner]}>
                            {fill(messages.pages.conflicts.pair.judge, {
                              winner: labelOf(CONFLICT_WINNER_LABEL, row.judge_winner),
                            })}
                            {row.judge_confidence != null ? ` (${row.judge_confidence.toFixed(2)})` : ""}
                          </Badge>
                        ) : null}
                      </div>
                      {row.judge_reason ? (
                        <p className="text-xs text-(--color-muted)">
                          {fill(messages.pages.conflicts.pair.judgeReason, { reason: row.judge_reason })}
                        </p>
                      ) : null}
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={ask.isPending}
                          title={messages.pages.conflicts.pair.previewTitle}
                          onClick={() => ask.mutate({ tag_id: row.tag_id, entity_id: row.entity_id })}
                        >
                          {ACTION.preview.label}
                        </Button>
                      </div>
                    </CardBody>
                  </Card>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {view === "decididos" && judged.data && (judged.data.items ?? []).length === 0 ? (
          <EmptyState
            title={messages.pages.conflicts.judged.emptyTitle}
            hint={messages.pages.conflicts.judged.emptyHint}
          />
        ) : null}

        {view === "decididos" && judged.data ? (
          <>
            <div className="flex flex-wrap gap-2 text-xs text-(--color-muted)">
              <Badge tone="ok">
                {fill(messages.pages.conflicts.judged.statsAutoResolved, {
                  count: formatCount(judged.data.auto_resolved),
                })}
              </Badge>
              <Badge tone="warn">
                {fill(messages.pages.conflicts.judged.statsSentToHuman, {
                  count: formatCount(judged.data.sent_to_human),
                })}
              </Badge>
              <Badge tone="accent">
                {fill(messages.pages.conflicts.judged.statsTagWins, { count: formatCount(judged.data.tag_wins) })}
              </Badge>
              <Badge tone="neutral">
                {fill(messages.pages.conflicts.judged.statsEntityWins, {
                  count: formatCount(judged.data.entity_wins),
                })}
              </Badge>
            </div>
            <ul className="grid gap-2">
              {(judged.data.items ?? []).map((item) => (
                <li key={item.queue_id}>
                  <Card className={item.applicable ? undefined : "opacity-80"}>
                    <CardBody className="grid gap-2">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="truncate text-sm font-medium">{item.tag_name}</span>
                        <span className="text-(--color-muted)">×</span>
                        <span className="truncate text-sm font-medium">{item.entity_name}</span>
                        <Badge tone={item.judge_winner ? CONFLICT_WINNER_TONE[item.judge_winner] : "neutral"}>
                          {item.judge_winner
                            ? CONFLICT_WINNER_LABEL[item.judge_winner]
                            : messages.pages.conflicts.judged.noVerdict}
                        </Badge>
                        {item.judge_confidence != null ? (
                          <Badge tone="neutral">{item.judge_confidence.toFixed(2)}</Badge>
                        ) : null}
                        <Badge tone={item.judge_status === "AI_APPROVED" ? "ok" : "warn"}>
                          {item.judge_status === "AI_APPROVED"
                            ? messages.pages.conflicts.judged.autoResolved
                            : messages.pages.conflicts.judged.humanReview}
                        </Badge>
                        {item.applicable ? (
                          <Badge tone="accent">{messages.pages.conflicts.judged.stillDecidable}</Badge>
                        ) : null}
                      </div>
                      {item.judge_reason ? <p className="text-xs text-(--color-muted)">{item.judge_reason}</p> : null}
                      <p className="text-xs text-(--color-muted)">
                        {fill(messages.pages.conflicts.judged.liveness, {
                          tag: item.tag_alive
                            ? messages.pages.conflicts.judged.tagAlive
                            : messages.pages.conflicts.judged.tagGone,
                          entity: item.entity_alive
                            ? messages.pages.conflicts.judged.entityAlive
                            : messages.pages.conflicts.judged.entityGone,
                        })}
                      </p>
                    </CardBody>
                  </Card>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {view === "resolucoes" && ledger.data && (ledger.data.items ?? []).length === 0 ? (
          <EmptyState
            title={messages.pages.conflicts.ledger.emptyTitle}
            hint={messages.pages.conflicts.ledger.emptyHint}
          />
        ) : null}

        {view === "resolucoes" && ledger.data ? (
          <ul className="grid gap-2">
            {(ledger.data.items ?? []).map((entry) => (
              <li key={entry.resolution_id}>
                <Card className={entry.is_undone ? "opacity-80" : undefined}>
                  <CardBody className="grid gap-2">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <code className="text-[10px] text-(--color-muted)">#{entry.resolution_id}</code>
                      <span className="truncate text-sm font-medium">{entry.tag_name}</span>
                      <span className="text-(--color-muted)">×</span>
                      <span className="truncate text-sm font-medium">{entry.entity_name}</span>
                      <Badge tone={CONFLICT_WINNER_TONE[entry.winner]}>
                        {fill(messages.pages.conflicts.ledger.won, { winner: labelOf(CONFLICT_WINNER_LABEL, entry.winner) })}
                      </Badge>
                      <Badge tone={entry.source === "JUDGE" ? "accent" : "ok"}>
                        {entry.source === "JUDGE"
                          ? messages.pages.conflicts.ledger.sourceJudge
                          : messages.pages.conflicts.ledger.sourceCuration}
                      </Badge>
                      {entry.is_undone ? (
                        <Badge tone="neutral">{messages.pages.conflicts.ledger.undone}</Badge>
                      ) : null}
                    </div>
                    <p className="text-xs text-(--color-muted)">
                      {fill(messages.pages.conflicts.ledger.linksCreated, {
                        count: formatCount(entry.documents_transferred),
                      })}
                      {entry.ban_kind ? (
                        <>
                          <Trans
                            text={messages.pages.conflicts.ledger.banLine}
                            values={{
                              kind: <code>{entry.ban_kind}</code>,
                              term: <code>{entry.ban_term}</code>,
                            }}
                          />
                          {entry.ban_created
                            ? messages.pages.conflicts.ledger.banCreated
                            : messages.pages.conflicts.ledger.banExisted}
                        </>
                      ) : null}
                      {entry.decided_by
                        ? fill(messages.pages.conflicts.ledger.decidedBy, { name: entry.decided_by })
                        : ""}
                      {entry.decided_at
                        ? fill(messages.pages.conflicts.ledger.decidedAt, {
                            date: formatDateTime(entry.decided_at),
                          })
                        : ""}
                    </p>
                    {entry.note ? (
                      <p className="text-xs text-(--color-muted)">
                        {fill(messages.pages.conflicts.ledger.note, { note: entry.note })}
                      </p>
                    ) : null}
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={entry.is_undone || undo.isPending}
                        title={
                          entry.is_undone
                            ? messages.pages.conflicts.ledger.undoDoneTitle
                            : messages.pages.conflicts.ledger.undoTitle
                        }
                        onClick={() => undo.mutate(entry.resolution_id)}
                      >
                        {ACTION.undo.label}
                      </Button>
                      {entry.is_undone ? (
                        <span className="text-xs text-(--color-muted)">
                          {messages.pages.conflicts.ledger.undone}
                          {entry.undone_by
                            ? fill(messages.pages.conflicts.ledger.undoneBy, { name: entry.undone_by })
                            : ""}
                          {entry.loser_restored
                            ? messages.pages.conflicts.ledger.recordRestored
                            : messages.pages.conflicts.ledger.recordNotRestored}
                        </span>
                      ) : null}
                    </div>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ul>
        ) : null}

        {total > CONFLICTS_PAGE_SIZE ? (
          <div className="flex items-center justify-between text-sm">
            <Button
              size="sm"
              disabled={page === 0}
              onClick={() =>
                navigate({ to: "/entidades/conflitos", search: { ...search, pagina: page - 1 || undefined } })
              }
            >
              {messages.common.previous}
            </Button>
            <span className="text-xs text-(--color-muted)">
              {fill(messages.pages.conflicts.pageOf, {
                page: formatCount(page + 1),
                lastPage: formatCount(lastPage),
                total: formatCount(total),
              })}
            </span>
            <Button
              size="sm"
              disabled={(page + 1) * CONFLICTS_PAGE_SIZE >= total}
              onClick={() => navigate({ to: "/entidades/conflitos", search: { ...search, pagina: page + 1 } })}
            >
              {messages.common.next}
            </Button>
          </div>
        ) : null}

        <p className="text-xs text-(--color-muted)">
          <Trans
            text={messages.pages.conflicts.footer}
            values={{
              that: <em>{messages.pages.conflicts.footerThat}</em>,
              judged: <em>{messages.pages.conflicts.footerJudgedTab}</em>,
            }}
          />
        </p>
      </PageBody>
    </>
  );
}

/**
 * What the batch wrote, what it left, and what it skipped.
 *
 * Three counts and never two: a pair an earlier pair of the same batch already finished is *work
 * done*, not an error, and mixing it into a failure count is how a clean batch starts reading like a
 * broken one. The list of skipped pairs keeps the reason, so the archivist can see which ones they
 * were. Every applied pair carries the `resolution_id` its own desfazer needs — the write is still
 * per pair even though the click was categorical.
 */
function BatchReport({ result }: { result: ConflictBatchResult }) {
  const messages = useCopy();
  const skipped = result.skipped ?? [];
  const failed = result.failed ?? [];

  return (
    <Card className="ring-1 ring-(--color-line)">
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{messages.pages.conflicts.batchResult.title}</span>
          <Badge tone="ok">
            {fill(messages.pages.conflicts.batchResult.resolved, {
              count: formatCount(result.applied?.length ?? 0),
            })}
          </Badge>
          <Badge tone="neutral">
            {fill(messages.pages.conflicts.batchResult.skipped, { count: formatCount(skipped.length) })}
          </Badge>
          {failed.length ? (
            <Badge tone="warn">
              {fill(messages.pages.conflicts.batchResult.failed, { count: formatCount(failed.length) })}
            </Badge>
          ) : null}
          <Badge tone="accent">
            {fill(messages.pages.conflicts.batchResult.remaining, {
              count: formatCount(result.remaining?.total ?? 0),
            })}
          </Badge>
        </div>
        {skipped.length ? (
          <ul className="grid gap-1 text-xs text-(--color-muted)">
            {skipped.slice(0, 10).map((item) => (
              <li key={`${item.tag_id}-${item.entity_id}`}>
                {item.tag_name} × {item.entity_name} — {item.reason}
              </li>
            ))}
          </ul>
        ) : null}
        {failed.length ? (
          <ul className="grid gap-1 text-xs text-(--color-muted)">
            {failed.slice(0, 10).map((item) => (
              <li key={`${item.tag_id}-${item.entity_id}`}>
                {item.tag_name} × {item.entity_name} — {item.reason}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="text-xs text-(--color-muted)">
          <Trans
            text={messages.pages.conflicts.batchResult.report}
            values={{ ledger: <em>{messages.pages.conflicts.view.resolucoes.label}</em> }}
          />
        </p>
      </CardBody>
    </Card>
  );
}

/**
 * The impact of both verdicts, shown before anything is written.
 *
 * The numbers come from the same planner the write executes, so the preview cannot promise a
 * different number from the apply. It is a panel and not a modal: the archivist is comparing two
 * verdicts, and a popup over the pair would hide the evidence being compared.
 */
function PreviewPanel({
  plan,
  note,
  pending,
  onNote,
  onCancel,
  onConfirm,
}: {
  plan: ConflictResolutionPlan;
  note: string;
  pending: boolean;
  onNote: (value: string) => void;
  onCancel: () => void;
  onConfirm: (winner: ConflictWinner) => void;
}) {
  const messages = useCopy();

  return (
    <Card className="ring-2 ring-(--color-accent)/30">
      <CardBody className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{messages.pages.conflicts.preview.title}</span>
          <Badge tone="accent">
            {fill(messages.pages.conflicts.preview.subject, { name: plan.tag_name })}
          </Badge>
          <Badge tone="ok">
            {fill(messages.pages.conflicts.preview.entity, {
              type: labelOf(ENTITY_TYPE_LABEL, plan.entity_type),
              name: plan.entity_name,
            })}
          </Badge>
          <Badge tone="neutral">
            {fill(messages.pages.conflicts.preview.similarity, { value: plan.similarity.toFixed(3) })}
          </Badge>
        </div>

        {plan.already_resolved ? (
          <Notice tone="warn">{messages.pages.conflicts.preview.alreadyResolved}</Notice>
        ) : null}

        {plan.judge_winner ? (
          <p className="text-xs text-(--color-muted)">
            <Trans
              text={messages.pages.conflicts.preview.judgeOpinion}
              values={{
                winner: <strong>{CONFLICT_WINNER_LABEL[plan.judge_winner]}</strong>,
                confidence:
                  plan.judge_confidence != null
                    ? fill(messages.pages.conflicts.preview.judgeConfidence, {
                        value: plan.judge_confidence.toFixed(2),
                      })
                    : "",
                reason: plan.judge_reason
                  ? fill(messages.pages.conflicts.preview.judgeReason, { reason: plan.judge_reason })
                  : "",
              }}
            />
          </p>
        ) : null}

        {!plan.resolvable ? (
          <Notice tone="warn">
            {plan.blocker}
          </Notice>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            <VerdictCard
              title={fill(messages.pages.conflicts.verdict.title, { winner: labelOf(CONFLICT_WINNER_LABEL, "TAG") })}
              tone="accent"
              loses={plan.tag_wins_loses}
              transferred={plan.tag_wins_documents_transferred}
              alreadyLinked={plan.tag_wins_documents_already_linked}
              banTerm={plan.tag_wins_ban_term}
              banExists={plan.tag_wins_ban_exists}
              banKind="NER_EXCLUSION"
              hint={CONFLICT_WINNER_HINT.TAG}
            />
            <VerdictCard
              title={fill(messages.pages.conflicts.verdict.title, { winner: labelOf(CONFLICT_WINNER_LABEL, "ENTITY") })}
              tone="ok"
              loses={plan.entity_wins_loses}
              transferred={plan.entity_wins_documents_transferred}
              alreadyLinked={plan.entity_wins_documents_already_linked}
              banTerm={plan.entity_wins_ban_term}
              banExists={plan.entity_wins_ban_exists}
              banKind="STOPWORD"
              hint={CONFLICT_WINNER_HINT.ENTITY}
            />
          </div>
        )}

        <div className="grid gap-2 sm:grid-cols-2">
          <Field label={messages.pages.conflicts.noteField}>
            <Input value={note} onChange={(event) => onNote(event.target.value)} />
          </Field>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            disabled={pending || !plan.resolvable || !plan.tag_alive || !plan.entity_alive}
            title={CONFLICT_WINNER_HINT.TAG}
            onClick={() => onConfirm("TAG")}
          >
            {fill(messages.pages.conflicts.preview.apply, {
              verb: ACTION.apply.label,
              winner: labelOf(CONFLICT_WINNER_LABEL, "TAG"),
            })}
          </Button>
          <Button
            variant="primary"
            disabled={pending || !plan.resolvable || !plan.tag_alive || !plan.entity_alive}
            title={CONFLICT_WINNER_HINT.ENTITY}
            onClick={() => onConfirm("ENTITY")}
          >
            {fill(messages.pages.conflicts.preview.apply, {
              verb: ACTION.apply.label,
              winner: labelOf(CONFLICT_WINNER_LABEL, "ENTITY"),
            })}
          </Button>
          <Button variant="ghost" disabled={pending} onClick={onCancel}>
            {ACTION.cancel.label}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function VerdictCard({
  title,
  tone,
  loses,
  transferred,
  alreadyLinked,
  banTerm,
  banExists,
  banKind,
  hint,
}: {
  title: string;
  tone: "accent" | "ok";
  loses: string | null | undefined;
  transferred: number;
  alreadyLinked: number;
  banTerm: string | null | undefined;
  banExists: boolean;
  banKind: string;
  hint: string | undefined;
}) {
  const messages = useCopy();

  return (
    <div className="grid gap-1 rounded-md bg-black/[0.02] px-3 py-2 text-xs ring-1 ring-(--color-line)">
      <Badge tone={tone}>{title}</Badge>
      <p className="text-(--color-muted)">
        <Trans
          text={messages.pages.conflicts.verdict.linksNew}
          values={{ count: <strong className="text-(--color-ink)">{formatCount(transferred)}</strong> }}
        />
        {alreadyLinked > 0
          ? fill(messages.pages.conflicts.verdict.linksAlready, { count: formatCount(alreadyLinked) })
          : ""}
      </p>
      {loses ? (
        <p className="text-(--color-muted)">
          <Trans text={messages.pages.conflicts.verdict.loses} values={{ term: <code>{loses}</code> }} />
        </p>
      ) : null}
      {banTerm ? (
        <p className="text-(--color-muted)">
          <Trans
            text={messages.pages.conflicts.verdict.banLine}
            values={{ kind: <code>{banKind}</code>, term: <code>{banTerm}</code> }}
          />
          {banExists
            ? messages.pages.conflicts.verdict.banExists
            : messages.pages.conflicts.verdict.banWillCreate}
        </p>
      ) : null}
      <p className="text-(--color-muted)">{hint}</p>
    </div>
  );
}

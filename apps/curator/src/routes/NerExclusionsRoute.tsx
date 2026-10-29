import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import {
  banNerExclusions,
  previewNerPurge,
  purgeNerExclusions,
  unbanNerExclusions,
  undoNerPurge,
  type NerPurgePreview,
} from "@/api/client";
import { MERGE_LOG_PAGE_SIZE, queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { LedgerList } from "@/components/ui/LedgerList";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { Trans } from "@/i18n/trans";
import { ACTION } from "@/lib/copy";
import { EXCLUSION_SOURCE_HINT, EXCLUSION_SOURCE_LABEL } from "@/lib/entities";
import { formatCount, formatDateTime } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";
import { routeMessage } from "@/lib/messages";
import { useDebounced } from "@/lib/useDebounced";

/**
 * The NER veto: "this spelling is a subject, not a proper name".
 *
 * The screen keeps two things apart that used to be one click (#94), and each is stated where it
 * matters:
 *
 * * **vetoing deletes nothing.** It records the decision and stops the extractor from creating the
 *   term from now on, and the list's "remover" re-opens it. The block is **by token boundary, not by
 *   exact name**: spaCy merges neighbouring tokens, so with ``iptu`` banned the model still returns
 *   ``"IPTU do Batel"`` as one entity, and an exact comparison would let the false positive through;
 * * **the purge is the destructive half, and it is a separate act.** It deletes the entities already
 *   extracted from a banned spelling, with their links, and it is the one thing here that reaches
 *   backwards. It runs behind its own preview and keeps a ledger, so the undo restores the entity,
 *   its links and its spellings — and does not lift the veto.
 *
 * It is also the *other half* of the bidirectional governance: this list records the curator or the
 * judge saying "this belongs to the subject axis", and it is stored apart from the subject-axis
 * stopwords on purpose — a veto here can never make the subject purge delete a tag the curator kept.
 */
export function NerExclusionsRoute() {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const exclusions = useQuery(queries.nerExclusions());

  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<NerPurgePreview | null>(null);
  const [purged, setPurged] = useState<number | null>(null);
  const [purgeIds, setPurgeIds] = useState<number[]>([]);
  const [logTerm, setLogTerm] = useState("");
  const [logLimit, setLogLimit] = useState(MERGE_LOG_PAGE_SIZE);
  const settledLogTerm = useDebounced(logTerm);

  const log = useQuery(queries.nerPurgeLog(logLimit, settledLogTerm.trim() || undefined));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "ner-exclusions"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "ner-purge-log"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "entities"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "conflicts"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const ban = useMutation({
    mutationFn: () =>
      banNerExclusions({
        words: draft
          .split(/[,\n]/)
          .map((word) => word.trim())
          .filter(Boolean),
        reason: reason.trim() || null,
      }),
    onSuccess: () => {
      setDraft("");
      setReason("");
      invalidate();
    },
  });

  const unban = useMutation({
    mutationFn: (word: string) => unbanNerExclusions({ words: [word] }),
    onSuccess: invalidate,
  });

  const dryRun = useMutation({
    mutationFn: previewNerPurge,
    onSuccess: (data) => {
      setPreview(data);
      setPurged(null);
      setPurgeIds([]);
    },
  });

  const purge = useMutation({
    mutationFn: purgeNerExclusions,
    onSuccess: (data) => {
      setPurged(data.entities_deleted);
      setPurgeIds(data.purge_ids ?? []);
      setPreview(null);
      invalidate();
    },
  });

  const revertPurge = useMutation({
    mutationFn: (purgeId: number) => undoNerPurge(purgeId),
    onSuccess: () => {
      setPurgeIds([]);
      invalidate();
    },
  });

  const rows = exclusions.data ?? [];
  const fromJudge = rows.filter((row) => row.source === "JUDGE").length;
  const fromHuman = rows.filter((row) => row.source === "HUMAN").length;

  return (
    <>
      <PageHeader
        screen="nerExclusions"
        pending={exclusions.isPending}
        status={
          exclusions.data
            ? fill(messages.pages.nerExclusions.status, {
                terms: formatCount(rows.length),
                judge: formatCount(fromJudge),
                curator: formatCount(fromHuman),
              })
            : undefined
        }
      />

      <PageBody>
        <Notice tone="warn">
          <Trans
            text={messages.pages.nerExclusions.notice}
            values={{
              lead: <strong>{messages.pages.nerExclusions.noticeLead}</strong>,
              first: <code>{messages.pages.nerExclusions.noticeFirstExample}</code>,
              second: <code>{messages.pages.nerExclusions.noticeSecondExample}</code>,
              warning: <strong>{messages.pages.nerExclusions.noticeWarning}</strong>,
            }}
          />
        </Notice>

        {/*
          The write first. The card used to be the last thing on the page: on a screen whose single
          job is "record that this spelling is not a name", the archivist had to scroll the whole
          record to find the form. It stays collapsed so the list of decisions remains the first thing
          read, and the labelled button is what makes it findable.
        */}
        <Disclosure
          triggerLabel={messages.pages.nerExclusions.form.trigger}
          toggleLabel={messages.pages.nerExclusions.form.toggle}
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">{messages.pages.nerExclusions.form.title}</span>
              <span className="text-xs text-(--color-muted)">{messages.pages.nerExclusions.form.hint}</span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">{messages.pages.nerExclusions.form.body}</p>
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={messages.pages.nerExclusions.form.placeholder}
            />
            <Textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder={messages.pages.nerExclusions.form.reasonPlaceholder}
              rows={2}
            />
            <div>
              <Button
                variant="primary"
                disabled={draft.trim().length === 0 || ban.isPending}
                onClick={() => ban.mutate()}
              >
                {ban.isPending
                  ? messages.pages.nerExclusions.form.pending
                  : messages.pages.nerExclusions.form.submit}
              </Button>
            </div>
            {ban.data ? (
              <p className="text-xs text-(--color-muted)">
                {routeMessage(ban.data)}{" "}
                {ban.data.created > 0
                  ? messages.pages.nerExclusions.form.created
                  : messages.pages.nerExclusions.form.already}
              </p>
            ) : null}
            {ban.error ? <ErrorState error={ban.error} /> : null}
            {unban.error ? <ErrorState error={unban.error} /> : null}
          </div>
        </Disclosure>

        {exclusions.error ? <ErrorState error={exclusions.error} /> : null}
        {exclusions.isPending ? <Spinner /> : null}

        {exclusions.data && rows.length === 0 ? (
          <EmptyState
            title={messages.pages.nerExclusions.emptyTitle}
            hint={
              <Trans
                text={messages.pages.nerExclusions.emptyHint}
                values={{
                  conflicts: (
                    <Link to="/entidades/conflitos" className="underline">
                      {messages.screens.conflicts.label}
                    </Link>
                  ),
                }}
              />
            }
          />
        ) : null}

        {rows.length > 0 ? (
          <Card>
            <CardBody>
              <LedgerList
                items={rows}
                keyOf={(row) => row.term}
                termOf={(row) => [row.term, row.reason ?? "", labelOf(EXCLUSION_SOURCE_LABEL, row.source)]}
                searchPlaceholder={messages.pages.nerExclusions.searchPlaceholder}
                nounSingular={messages.pages.nerExclusions.nounSingular}
                nounPlural={messages.pages.nerExclusions.nounPlural}
                emptyTitle={messages.pages.nerExclusions.emptyTitle}
                renderItem={(row) => (
                  <div className="grid gap-1 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="flex min-w-0 flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">{row.term}</span>
                        <Badge
                          tone={row.source === "JUDGE" ? "accent" : "ok"}
                          title={EXCLUSION_SOURCE_HINT[row.source]}
                        >
                          {labelOf(EXCLUSION_SOURCE_LABEL, row.source)}
                        </Badge>
                        {row.tag_id !== null ? (
                          <Badge tone="neutral" title={messages.pages.nerExclusions.tagBadgeTitle}>
                            {fill(messages.pages.nerExclusions.tagId, { id: row.tag_id })}
                          </Badge>
                        ) : null}
                        <span className="text-xs text-(--color-muted)">{formatDateTime(row.created_at)}</span>
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={unban.isPending}
                        title={messages.pages.nerExclusions.unbanTitle}
                        onClick={() => unban.mutate(row.term)}
                      >
                        {ACTION.remove.label}
                      </Button>
                    </div>
                    {row.reason ? <p className="text-xs text-(--color-muted)">{row.reason}</p> : null}
                  </div>
                )}
              />
            </CardBody>
          </Card>
        ) : null}

        <Card className="ring-(--color-danger)/30">
          <CardHeader className="text-sm font-semibold text-(--color-danger)">
            {messages.pages.nerExclusions.purge.title}
          </CardHeader>
          <CardBody className="grid gap-3">
            <p className="text-xs text-(--color-muted)">
              <Trans
                text={messages.pages.nerExclusions.purge.body}
                values={{ ledger: <strong>{messages.pages.nerExclusions.purge.bodyLedger}</strong> }}
              />
            </p>

            <div className="flex flex-wrap items-center gap-2">
              <Button disabled={dryRun.isPending || purge.isPending} onClick={() => dryRun.mutate()}>
                {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
              </Button>
              <Button
                variant="danger"
                disabled={!preview || preview.total_entities === 0 || purge.isPending}
                title={preview ? undefined : messages.pages.nerExclusions.purge.previewRequired}
                onClick={() => purge.mutate()}
              >
                {purge.isPending
                  ? ACTION.exclude.pending
                  : preview
                    ? fill(messages.pages.nerExclusions.purge.purgeCount, {
                        count: formatCount(preview.total_entities),
                      })
                    : messages.pages.nerExclusions.purge.purgeFirst}
              </Button>
            </div>

            {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
            {purge.error ? <ErrorState error={purge.error} /> : null}

            {preview ? (
              <Notice tone="danger" as="div" className="grid gap-2">
                <p>
                  <Trans
                    text={messages.pages.nerExclusions.purge.previewLead}
                    values={{
                      entities: (
                        <strong>
                          {fill(messages.pages.nerExclusions.purge.previewEntities, {
                            count: formatCount(preview.total_entities),
                          })}
                        </strong>
                      ),
                      links: (
                        <strong>
                          {fill(messages.pages.nerExclusions.purge.previewLinks, {
                            count: formatCount(preview.total_documents),
                          })}
                        </strong>
                      ),
                    }}
                  />
                </p>
                {(preview.excluded_terms ?? []).length > 0 ? (
                  <p className="text-(--color-muted)">
                    {messages.pages.nerExclusions.purge.reached}{" "}
                    <code>{(preview.excluded_terms ?? []).join(", ")}</code>
                  </p>
                ) : null}
                {preview.total_entities === 0 ? (
                  <p className="text-(--color-muted)">{messages.pages.nerExclusions.purge.nothingToPurge}</p>
                ) : (
                  <ul className="max-h-64 overflow-y-auto">
                    {(preview.entities ?? []).map((entity) => (
                      <li key={entity.entity_id} className="flex items-center justify-between gap-3 py-0.5">
                        <span className="truncate">
                          {entity.name} <span className="text-(--color-muted)">· {entity.entity_type}</span>
                        </span>
                        <span className="shrink-0 tabular-nums text-(--color-muted)">
                          {fill(messages.pages.nerExclusions.purge.documents, {
                            count: formatCount(entity.document_count),
                          })}
                          {(entity.synonym_names ?? []).length > 0
                            ? ` · ${fill(messages.pages.nerExclusions.purge.synonyms, {
                                count: formatCount((entity.synonym_names ?? []).length),
                              })}`
                            : ""}
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
                  {fill(messages.pages.nerExclusions.purge.purged, { count: formatCount(purged) })}
                </p>
                {purgeIds.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={revertPurge.isPending}
                      title={messages.pages.nerExclusions.purge.undoTitle}
                      onClick={() => {
                        const [first] = purgeIds;
                        if (first !== undefined) revertPurge.mutate(first);
                      }}
                    >
                      {messages.pages.nerExclusions.purge.undo}
                    </Button>
                    <span className="text-(--color-muted)">
                      {messages.pages.nerExclusions.purge.entries} <code>{purgeIds.join(", ")}</code>
                    </span>
                  </div>
                ) : null}
              </Notice>
            ) : null}
            {revertPurge.error ? <ErrorState error={revertPurge.error} /> : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader className="text-sm font-semibold">{messages.pages.nerExclusions.log.title}</CardHeader>
          <CardBody className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              <Trans
                text={messages.pages.nerExclusions.log.hint}
                values={{ strong: <strong>{messages.pages.nerExclusions.log.hintStrong}</strong> }}
              />
            </p>
            {/*
              The search is server-side: the ledger only grows, and a box that filtered the loaded page
              would say "não está aqui" for a purge that happened.
            */}
            <Input
              className="max-w-xs"
              value={logTerm}
              placeholder={messages.pages.nerExclusions.log.searchPlaceholder}
              onChange={(event) => setLogTerm(event.target.value)}
            />
            {log.isPending ? <Spinner label={messages.pages.nerExclusions.log.reading} /> : null}
            {log.error ? <ErrorState error={log.error} /> : null}
            {log.data && (log.data.items ?? []).length === 0 ? (
              <EmptyState
                title={
                  logTerm.trim()
                    ? fill(messages.pages.nerExclusions.log.emptyTerm, { term: logTerm.trim() })
                    : messages.pages.nerExclusions.log.empty
                }
                hint={
                  logTerm.trim()
                    ? messages.pages.nerExclusions.log.emptyTermHint
                    : messages.pages.nerExclusions.log.emptyHint
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
                      · {entry.entity_type} ·{" "}
                      {fill(messages.pages.nerExclusions.log.documents, {
                        count: formatCount(entry.document_count),
                      })}{" "}
                      · {formatDateTime(entry.changed_at)}
                      {entry.changed_by
                        ? ` ${fill(messages.pages.nerExclusions.log.by, { name: entry.changed_by })}`
                        : ""}{" "}
                      · {messages.pages.nerExclusions.log.veto} <code>{entry.excluded_term}</code>
                    </span>
                  </span>
                  {entry.undone_at ? (
                    <Badge tone="neutral">
                      {fill(messages.pages.nerExclusions.log.restored, {
                        date: formatDateTime(entry.undone_at),
                      })}
                    </Badge>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={revertPurge.isPending}
                      title={messages.pages.nerExclusions.log.undoTitle}
                      onClick={() => revertPurge.mutate(entry.purge_id)}
                    >
                      {messages.pages.nerExclusions.log.undo}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
            {/*
              The footer appears whenever there is something to say: more rows below, or a search that
              matched — the same rule the stopword purge ledger follows.
            */}
            {log.data && (log.data.total > (log.data.items ?? []).length || settledLogTerm.trim()) ? (
              <div className="flex items-center gap-2">
                {log.data.total > (log.data.items ?? []).length ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setLogLimit((current) => current + MERGE_LOG_PAGE_SIZE)}
                  >
                    {messages.pages.nerExclusions.log.seeMore}
                  </Button>
                ) : null}
                <span className="text-xs text-(--color-muted)">
                  {fill(
                    settledLogTerm.trim()
                      ? messages.pages.nerExclusions.log.showingFiltered
                      : messages.pages.nerExclusions.log.showing,
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
      </PageBody>
    </>
  );
}

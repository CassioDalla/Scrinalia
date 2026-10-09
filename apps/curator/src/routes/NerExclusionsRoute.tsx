import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { banNerExclusions, unbanNerExclusions } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { LedgerList } from "@/components/ui/LedgerList";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { ACTION } from "@/lib/copy";
import { EXCLUSION_SOURCE_HINT, EXCLUSION_SOURCE_LABEL } from "@/lib/entities";
import { formatCount, formatDateTime } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";
import { routeMessage } from "@/lib/messages";

/**
 * The NER veto: "this spelling is a subject, not a proper name".
 *
 * Two behaviours the screen has to state, because neither is visible in the list:
 *
 * * the block is **by token boundary, not by exact name**. spaCy merges neighbouring tokens, so with
 *   ``iptu`` banned the model still returns ``"IPTU do Batel"`` as one entity and an exact
 *   comparison would let the false positive through. The veto covers the whole term, not a piece of
 *   it;
 * * adding a veto **applies to the past**: the entities already extracted from that spelling are
 *   purged, and the links go with them by cascade. It is a decision with retroactive effect, which
 *   is why the reason is kept.
 *
 * It is also the *other half* of the bidirectional governance: this list records the curator or the
 * judge saying "this belongs to the subject axis", and it is stored apart from the subject-axis
 * stopwords on purpose — a veto here can never make the subject purge delete a tag the curator kept.
 */
export function NerExclusionsRoute() {
  const queryClient = useQueryClient();
  const exclusions = useQuery(queries.nerExclusions());

  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "ner-exclusions"] });
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
            ? `${formatCount(rows.length)} termos vetados · ${formatCount(fromJudge)} do juiz · ${formatCount(fromHuman)} da curadoria`
            : undefined
        }
      />

      <PageBody className="max-w-4xl">
        <Notice tone="warn">
          <strong>O veto vale para o termo inteiro, não para pedaços.</strong> O extrator funde tokens
          vizinhos: com <code>iptu</code> vetado ele ainda devolve <code>“IPTU do Batel”</code> como uma
          entidade, então o bloqueio é por limite de token. E ele <strong>vale para trás</strong>: as
          entidades já extraídas dessa grafia são excluídas, junto com os vínculos.
        </Notice>

        {/*
          The write first. The card used to be the last thing on the page: on a screen whose single
          job is "record that this spelling is not a name", the archivist had to scroll the whole
          record to find the form. It stays collapsed so the list of decisions remains the first thing
          read, and the labelled button is what makes it findable.
        */}
        <Disclosure
          triggerLabel="+ Vetar Termos"
          toggleLabel="Vetar termos"
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">Vetar Termos</span>
              <span className="text-xs text-(--color-muted)">
                O veto vale para o termo inteiro e exclui as entidades já extraídas dessa grafia.
              </span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Separe por vírgula ou quebra de linha. O motivo é guardado para auditoria — e ele é o que
              explica a decisão para quem abrir a lista depois.
            </p>
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="termos, separados por vírgula"
            />
            <Textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="por que este termo é assunto e não nome próprio"
              rows={2}
            />
            <div>
              <Button
                variant="primary"
                disabled={draft.trim().length === 0 || ban.isPending}
                onClick={() => ban.mutate()}
              >
                {ban.isPending ? "Vetando…" : "Vetar e expurgar do passado"}
              </Button>
            </div>
            {ban.data ? (
              <p className="text-xs text-(--color-muted)">
                {routeMessage(ban.data)} {formatCount(ban.data.entities_deleted)} entidades excluídas.
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
            title="Nenhum termo vetado"
            hint={
              <>
                O veto é a decisão “isto é assunto, não nome próprio”. Ele é escrito pelo juiz de
                conflitos em <Link to="/entidades/conflitos" className="underline">/entidades/conflitos</Link>{" "}
                ou por você aqui. Enquanto o NER não rodar no acervo, esta lista nasce vazia.
              </>
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
                searchPlaceholder="buscar termo vetado…"
                nounSingular="termo vetado"
                nounPlural="termos vetados"
                emptyTitle="Nenhum termo vetado"
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
                          <Badge tone="neutral" title="A tag que justifica a decisão">
                            tag #{row.tag_id}
                          </Badge>
                        ) : null}
                        <span className="text-xs text-(--color-muted)">{formatDateTime(row.created_at)}</span>
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={unban.isPending}
                        title="O extrator volta a considerar o termo"
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
      </PageBody>
    </>
  );
}

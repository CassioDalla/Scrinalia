import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { banNerExclusions, unbanNerExclusions } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Textarea } from "@/components/ui/Input";
import { EXCLUSION_SOURCE_HINT, EXCLUSION_SOURCE_LABEL } from "@/lib/entities";
import { formatCount, formatDateTime } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";

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
        title="Exclusões de NER"
        subtitle={
          exclusions.data
            ? `${formatCount(rows.length)} termos vetados · ${formatCount(fromJudge)} do juiz · ${formatCount(fromHuman)} da curadoria`
            : "Lendo as exclusões…"
        }
      />

      <div className="grid max-w-4xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
          <strong>O veto vale para o termo inteiro, não para pedaços.</strong> O extrator funde tokens
          vizinhos: com <code>iptu</code> vetado ele ainda devolve <code>“IPTU do Batel”</code> como uma
          entidade, então o bloqueio é por limite de token. E ele <strong>vale para trás</strong>: as
          entidades já extraídas dessa grafia são apagadas, junto com os vínculos.
        </p>

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

        <ul className="grid gap-2">
          {rows.map((row) => (
            <li key={row.term}>
              <Card>
                <CardBody className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{row.term}</span>
                    <Badge tone={row.source === "JUDGE" ? "accent" : "ok"} title={EXCLUSION_SOURCE_HINT[row.source]}>
                      {labelOf(EXCLUSION_SOURCE_LABEL, row.source)}
                    </Badge>
                    {row.tag_id !== null ? (
                      <Badge tone="neutral" title="A tag que justifica a decisão">
                        tag #{row.tag_id}
                      </Badge>
                    ) : null}
                    <span className="text-xs text-(--color-muted)">{formatDateTime(row.created_at)}</span>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={unban.isPending}
                    title="O extrator volta a considerar o termo"
                    onClick={() => unban.mutate(row.term)}
                  >
                    remover veto
                  </Button>
                </CardBody>
                {row.reason ? (
                  <CardBody className="pt-0 text-xs text-(--color-muted)">{row.reason}</CardBody>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>

        <Card>
          <CardHeader className="text-sm font-semibold">Vetar termos</CardHeader>
          <CardBody className="grid gap-2">
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
                {ban.data.message} {formatCount(ban.data.entities_deleted)} entidades apagadas.
              </p>
            ) : null}
            {ban.error ? <ErrorState error={ban.error} /> : null}
            {unban.error ? <ErrorState error={unban.error} /> : null}
          </CardBody>
        </Card>
      </div>
    </>
  );
}

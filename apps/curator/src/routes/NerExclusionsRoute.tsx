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
            ? `${formatCount(rows.length)} termos vetados · ${formatCount(fromJudge)} do juiz · ${formatCount(fromHuman)} da curadoria`
            : undefined
        }
      />

      <PageBody>
        <Notice tone="warn">
          <strong>O bloqueio se aplica à palavra exata inteira.</strong>
          A extração avalia expressões completas: ao bloquear "<code>IPTU</code>", um
          termo composto como "<code>IPTU do prédio</code>" também será ignorado, pois
          contém a palavra bloqueada. <strong>Bloquear um termo não remove os dados já existentes;</strong>
          para excluir as ocorrências anteriores, execute a limpeza
          retroativa, onde você pode revisar os impactos e desfazer ações
          pelo histórico.
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
                O veto vale para a palavra inteira. Ele não exclui nada: o expurgo do passado fica abaixo.
              </span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Separe por vírgula ou quebra de linha. O motivo fica guardado para auditoria e é o que
              explica a decisão a quem abrir a lista depois.
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
                {ban.isPending ? "Vetando…" : "Vetar termo"}
              </Button>
            </div>
            {ban.data ? (
              <p className="text-xs text-(--color-muted)">
                {routeMessage(ban.data)}{" "}
                {ban.data.created > 0
                  ? "Nada foi excluído: o que já existe sai no expurgo do passado, abaixo."
                  : "O termo já estava vetado."}
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
                O veto é a decisão “isto é assunto, não nome próprio”. Ele vem do juiz de conflitos, na
                tela <Link to="/entidades/conflitos" className="underline">Conflitos</Link>{" "}
                ou de você aqui. Enquanto a extração de nomes não rodar no acervo, esta lista nasce vazia.
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
                        title="A extração volta a considerar o termo. As entidades já expurgadas só voltam pelo histórico de expurgos, abaixo."
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
          <CardHeader className="text-sm font-semibold text-(--color-danger)">Expurgar do passado</CardHeader>
          <CardBody className="grid gap-3">
            <p className="text-xs text-(--color-muted)">
              O expurgo exclui toda entidade cujo nome seja um termo vetado. Os vínculos com as
              descrições caem junto e o nome sai do vocabulário. Antes de sair, cada entidade excluída
              entra no <strong>histórico de expurgos</strong>{" "}
              — o desfazer restaura a entidade, os vínculos e as grafias, mas não levanta o veto.
            </p>

            <div className="flex flex-wrap items-center gap-2">
              <Button disabled={dryRun.isPending || purge.isPending} onClick={() => dryRun.mutate()}>
                {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
              </Button>
              <Button
                variant="danger"
                disabled={!preview || preview.total_entities === 0 || purge.isPending}
                title={preview ? undefined : "O impacto é obrigatório: confira o que seria excluído primeiro."}
                onClick={() => purge.mutate()}
              >
                {purge.isPending
                  ? ACTION.exclude.pending
                  : preview
                    ? `Expurgar ${formatCount(preview.total_entities)} entidade(s)`
                    : "Expurgar (confira antes)"}
              </Button>
            </div>

            {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
            {purge.error ? <ErrorState error={purge.error} /> : null}

            {preview ? (
              <Notice tone="danger" as="div" className="grid gap-2">
                <p>
                  Nada foi excluído ainda. Seriam <strong>{formatCount(preview.total_entities)} entidade(s)</strong>{" "}
                  em <strong>{formatCount(preview.total_documents)} vínculo(s)</strong>.
                </p>
                {(preview.excluded_terms ?? []).length > 0 ? (
                  <p className="text-(--color-muted)">
                    termos que o expurgo alcança: <code>{(preview.excluded_terms ?? []).join(", ")}</code>
                  </p>
                ) : null}
                {preview.total_entities === 0 ? (
                  <p className="text-(--color-muted)">
                    Nenhuma entidade do acervo tem um desses nomes — não há o que expurgar.
                  </p>
                ) : (
                  <ul className="max-h-64 overflow-y-auto">
                    {(preview.entities ?? []).map((entity) => (
                      <li key={entity.entity_id} className="flex items-center justify-between gap-3 py-0.5">
                        <span className="truncate">
                          {entity.name} <span className="text-(--color-muted)">· {entity.entity_type}</span>
                        </span>
                        <span className="shrink-0 tabular-nums text-(--color-muted)">
                          {formatCount(entity.document_count)} documento(s)
                          {(entity.synonym_names ?? []).length > 0
                            ? ` · ${formatCount((entity.synonym_names ?? []).length)} grafia(s)`
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
                <p>{formatCount(purged)} entidade(s) excluída(s) e registrada(s) no histórico de expurgos.</p>
                {purgeIds.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={revertPurge.isPending}
                      title="Restaura a entidade, os vínculos e as grafias deste expurgo. O veto continua."
                      onClick={() => {
                        const [first] = purgeIds;
                        if (first !== undefined) revertPurge.mutate(first);
                      }}
                    >
                      Desfazer este expurgo
                    </Button>
                    <span className="text-(--color-muted)">
                      entradas no histórico: <code>{purgeIds.join(", ")}</code>
                    </span>
                  </div>
                ) : null}
              </Notice>
            ) : null}
            {revertPurge.error ? <ErrorState error={revertPurge.error} /> : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader className="text-sm font-semibold">Histórico de expurgos</CardHeader>
          <CardBody className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Cada linha é uma entidade excluída pelo expurgo, com o que havia antes: nome, tipo,
              vínculos e grafias. O desfazer restaura a entidade — e <strong>não</strong> levanta o veto,
              que continua valendo na próxima extração.
            </p>
            {/*
              The search is server-side: the ledger only grows, and a box that filtered the loaded page
              would say "não está aqui" for a purge that happened.
            */}
            <Input
              className="max-w-xs"
              value={logTerm}
              placeholder="buscar por entidade expurgada…"
              onChange={(event) => setLogTerm(event.target.value)}
            />
            {log.isPending ? <Spinner label="Lendo o histórico…" /> : null}
            {log.error ? <ErrorState error={log.error} /> : null}
            {log.data && (log.data.items ?? []).length === 0 ? (
              <EmptyState
                title={logTerm.trim() ? `Nenhum expurgo para “${logTerm.trim()}”` : "Nenhum expurgo registrado ainda"}
                hint={
                  logTerm.trim()
                    ? "A busca cobre o nome da entidade expurgada."
                    : "O histórico registra cada entidade excluída, com o que havia antes."
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
                      · {entry.entity_type} · {formatCount(entry.document_count)} documento(s) ·{" "}
                      {formatDateTime(entry.changed_at)}
                      {entry.changed_by ? ` · por ${entry.changed_by}` : ""} · veto <code>{entry.excluded_term}</code>
                    </span>
                  </span>
                  {entry.undone_at ? (
                    <Badge tone="neutral">restaurada em {formatDateTime(entry.undone_at)}</Badge>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={revertPurge.isPending}
                      title="Restaura a entidade, os vínculos e as grafias. O veto do termo continua."
                      onClick={() => revertPurge.mutate(entry.purge_id)}
                    >
                      Desfazer
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
                    ver mais
                  </Button>
                ) : null}
                <span className="text-xs text-(--color-muted)">
                  mostrando {formatCount((log.data.items ?? []).length)} de {formatCount(log.data.total)}{" "}
                  {settledLogTerm.trim() ? "expurgo(s) que casam com a busca" : "expurgo(s) registrado(s)"}
                </span>
              </div>
            ) : null}
          </CardBody>
        </Card>
      </PageBody>
    </>
  );
}

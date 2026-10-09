import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { excludeFromSubjects, restoreToSubjects } from "@/api/client";
import { SUBJECT_SUGGESTIONS_PAGE_SIZE, queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { LedgerList } from "@/components/ui/LedgerList";
import { ACTION } from "@/lib/copy";
import { descricoes, formatCount } from "@/lib/format";
import { SIGNAL_HINT, SIGNAL_LABEL } from "@/lib/quality";
import { routeMessage } from "@/lib/messages";

/**
 * The curated half of ``NENHUMA``: "this is not a subject at all".
 *
 * The deterministic guard catches what has a *shape* — a date, a placeholder, a street name, a bare
 * number — and on real measurement it caught **1 of 4** of the hand-labelled non-subjects. The rest
 * are semantic calls no rule resolves: ``pessoas`` reaches 166 documents, ``vista aérea`` 89 and
 * ``capanema`` 91. Those are the cases this screen exists for.
 *
 * Banning here **deletes nothing**: the term stays a tag, stays linked to its descriptions and stays
 * reachable by search. Only the subject classification stops guessing at it — which is exactly how
 * "the model answers confidently and wrongly" turns into "the curator decided".
 */
export function SubjectExclusionsRoute() {
  const queryClient = useQueryClient();
  const exclusions = useQuery(queries.subjectExclusions());
  const [showRecorded, setShowRecorded] = useState(false);
  const [offset, setOffset] = useState(0);
  const suggestions = useQuery(queries.subjectExclusionSuggestions(showRecorded, offset));

  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "subject-exclusions"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "subject-exclusion-suggestions"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  /**
   * One write for both halves: the field (a human judgement, ``source=HUMAN``) and the candidate
   * list (the guard's shape, ``source=RULE``). They differ in where the verdict came from, and the
   * column exists so a later reader can tell a shape from a judgement.
   */
  const ban = useMutation({
    mutationFn: (body?: { words: string[]; reason: string | null; source: "HUMAN" | "RULE" }) =>
      excludeFromSubjects(
        body ?? {
          words: draft
            .split(/[,\n]/)
            .map((word) => word.trim())
            .filter(Boolean),
          reason: reason.trim() || null,
          source: "HUMAN",
        },
      ),
    onSuccess: () => {
      setDraft("");
      setReason("");
      invalidate();
    },
  });

  const restore = useMutation({
    mutationFn: (word: string) => restoreToSubjects({ words: [word] }),
    onSuccess: invalidate,
  });

  const words = exclusions.data ?? [];

  return (
    <>
      <PageHeader
        screen="subjectExclusions"
        pending={exclusions.isPending}
        status={exclusions.data ? `${formatCount(words.length)} termos fora do eixo de assunto` : undefined}
        actions={
          <Link to="/assuntos/tags">
            <Button size="sm">Tags</Button>
          </Link>
        }
      />

      <div className="grid max-w-4xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-accent)/5 px-3 py-2 text-xs text-(--color-accent) ring-1 ring-(--color-accent)/20">
          O guard determinístico pega o que tem forma — data, placeholder, logradouro, número — e na
          medição real ele pegou <strong>1 de 4</strong> dos não-assuntos do gabarito. O resto é
          julgamento semântico que nenhuma regra resolve. <strong>Banir não apaga nada:</strong> a tag
          continua no acervo e alcançável pela busca; só a classificação de assunto para de adivinhar.
        </p>

        {/*
          The computed candidates, not three hardcoded examples.

          The guard already refuses 1.489 of the real tags inside the classifier and nothing recorded
          it; this is the list it produces, with the evidence the archivist decides with. The three
          hand-labelled cases no rule reaches are named in the empty state instead of being offered as
          buttons, because the route deliberately proposes nothing for them.
        */}
        {suggestions.data ? (
          <section className="grid gap-2">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div className="grid gap-1">
                <span className="text-sm font-semibold">O guarda já recusa estes termos</span>
                <span className="text-xs text-(--color-muted)">
                  {formatCount(suggestions.data.candidate_count)} candidatos ·{" "}
                  {Object.entries(suggestions.data.by_signal ?? {})
                    .map(([signal, count]) => `${SIGNAL_LABEL[signal] ?? signal} ${formatCount(count)}`)
                    .join(" · ")}
                  {suggestions.data.place_count > 0
                    ? ` · ${formatCount(suggestions.data.place_count)} vão para a faceta Lugar`
                    : ""}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant={showRecorded ? "primary" : "ghost"}
                  title="Inclui os termos que já estão registrados como não-assunto, marcados como tais."
                  onClick={() => {
                    setShowRecorded((current) => !current);
                    setOffset(0);
                  }}
                >
                  {showRecorded ? "esconder os já registrados" : "mostrar os já registrados"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={suggestions.data.candidate_count === 0 || ban.isPending}
                  title="Registra de uma vez todos os candidatos do guarda, com source=RULE."
                  onClick={() =>
                    ban.mutate({
                      words: (suggestions.data?.items ?? [])
                        .filter((item) => !item.already_excluded)
                        .map((item) => item.term),
                      source: "RULE",
                      reason: "forma reconhecida pelo guarda determinístico (ano, placeholder, medida, logradouro ou nome de pessoa)",
                    })
                  }
                >
                  registrar os {formatCount(suggestions.data.candidate_count)} do guarda
                </Button>
              </div>
            </div>

            <ul className="grid gap-2">
              {(suggestions.data.items ?? []).map((item) => (
                <li key={item.term}>
                  <Card className={item.already_excluded ? "opacity-70" : undefined}>
                    <CardBody className="flex flex-wrap items-center justify-between gap-2">
                      <div className="grid gap-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <code className="text-sm font-medium">{item.term}</code>
                          <Badge tone="warn">{SIGNAL_LABEL[item.signal] ?? item.signal}</Badge>
                          <Badge tone="neutral">{descricoes(item.document_count)}</Badge>
                          {item.is_place_term ? (
                            <Badge tone="accent" title="O guarda recusa como assunto, mas a faceta Lugar o reivindica: 'não é assunto' não é 'vai para o lixo'.">
                              vai para a faceta Lugar
                            </Badge>
                          ) : null}
                          {item.also_an_entity ? (
                            <Badge tone="ok" title="A mesma grafia existe como entidade nomeada: isso é a tela de conflitos, não esta.">
                              também é entidade
                            </Badge>
                          ) : null}
                          {item.already_excluded ? <Badge tone="neutral">já registrado</Badge> : null}
                        </span>
                        {SIGNAL_HINT[item.signal] ? (
                          <span className="text-xs text-(--color-muted)">{SIGNAL_HINT[item.signal]}</span>
                        ) : null}
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={item.already_excluded || ban.isPending}
                        onClick={() =>
                          ban.mutate({
                            words: [item.term],
                            source: "RULE",
                            reason: `forma reconhecida pelo guarda: ${item.signal}`,
                          })
                        }
                      >
                        marcar como não-assunto
                      </Button>
                    </CardBody>
                  </Card>
                </li>
              ))}
            </ul>

            {suggestions.data.total > SUBJECT_SUGGESTIONS_PAGE_SIZE ? (
              <div className="flex items-center justify-between text-sm">
                <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - SUBJECT_SUGGESTIONS_PAGE_SIZE))}>
                  ← Anterior
                </Button>
                <span className="text-xs text-(--color-muted)">
                  página {formatCount(Math.floor(offset / SUBJECT_SUGGESTIONS_PAGE_SIZE) + 1)} de{" "}
                  {formatCount(Math.ceil(suggestions.data.total / SUBJECT_SUGGESTIONS_PAGE_SIZE))}
                </span>
                <Button
                  size="sm"
                  disabled={offset + SUBJECT_SUGGESTIONS_PAGE_SIZE >= suggestions.data.total}
                  onClick={() => setOffset(offset + SUBJECT_SUGGESTIONS_PAGE_SIZE)}
                >
                  Próxima →
                </Button>
              </div>
            ) : null}

            <p className="text-xs text-(--color-muted)">
              A metade semântica não é sugerida por ninguém, de propósito: <code>pessoas</code> (166
              documentos), <code>vista aérea</code> (89) e <code>capanema</code> (91) não têm forma que
              uma regra pegue, e o modelo — que não sabe se abster — responde com confiança justamente
              nesses. Eles entram pelo campo acima, que é julgamento humano.
            </p>
          </section>
        ) : null}

        {suggestions.error ? <ErrorState error={suggestions.error} /> : null}
        {suggestions.isPending ? <Spinner label="Aplicando o guarda ao vocabulário…" /> : null}

        {exclusions.error ? <ErrorState error={exclusions.error} /> : null}
        {exclusions.isPending ? <Spinner /> : null}

        {/*
          The write first, and the catalogue of decisions under it — the same order the tags screen
          uses for its stopwords. Banning here deletes nothing, so the record below is the whole point
          of the screen; the form stays collapsed and gets a labelled button to be findable.
        */}
        <Disclosure
          triggerLabel="+ Vetar termos"
          toggleLabel="Vetar termos"
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">Vetar termos</span>
              <span className="text-xs text-(--color-muted)">
                Banir não apaga nada: a tag continua no acervo, só a classificação de assunto para de adivinhar.
              </span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Para os termos que <strong>nenhuma regra alcança</strong> — os julgamentos semânticos. Os
              que o guarda já recusa estão na lista acima e entram por ela, com <code>source=RULE</code>{" "}
              e o motivo declarado.
            </p>
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="termos, separados por vírgula"
            />
            <Input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="motivo (guardado para auditoria)"
            />
            <div>
              <Button
                variant="primary"
                disabled={draft.trim().length === 0 || ban.isPending}
                onClick={() =>
                  ban.mutate({
                    words: draft
                      .split(/[,\n]/)
                      .map((word) => word.trim())
                      .filter(Boolean),
                    reason: reason.trim() || null,
                    source: "HUMAN",
                  })
                }
              >
                {ban.isPending ? "Vetando…" : "Marcar como não-assunto"}
              </Button>
            </div>
            {ban.data ? (
              <p className="text-xs text-(--color-muted)">
                {routeMessage(ban.data)} {formatCount(ban.data.created)} termo(s) registrado(s).
              </p>
            ) : null}
            {ban.error ? <ErrorState error={ban.error} /> : null}
          </div>
        </Disclosure>


        {exclusions.data && words.length === 0 ? (
          <EmptyState
            title="Nenhum termo excluído do eixo de assunto"
            hint="A lista nasce vazia: ela é feita de decisões humanas sobre casos que a regra não pega. Enquanto o classificador não rodar no acervo, também não há erro a corrigir."
          />
        ) : null}

        {words.length > 0 ? (
          <Card>
            <CardHeader className="text-sm font-semibold">Termos vetados</CardHeader>
            <CardBody>
              {/*
                A list with a search and not a cloud of chips: the chips read well at twenty and become a
                wall at two hundred, and finding the one term a colleague mentions is the whole reason
                anyone opens this screen a second time.
              */}
              <LedgerList
                items={words}
                keyOf={(word) => word}
                termOf={(word) => [word]}
                searchPlaceholder="buscar termo vetado…"
                nounSingular="termo vetado"
                nounPlural="termos vetados"
                emptyTitle="Nenhum termo vetado"
                renderItem={(word) => (
                  <div className="flex items-center justify-between gap-3 py-1.5">
                    <span className="truncate">{word}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={restore.isPending}
                      title="O classificador volta a considerar o termo"
                      onClick={() => restore.mutate(word)}
                    >
                      {ACTION.remove.label}
                    </Button>
                  </div>
                )}
              />
            </CardBody>
          </Card>
        ) : null}

        {restore.error ? <ErrorState error={restore.error} /> : null}

      </div>
    </>
  );
}

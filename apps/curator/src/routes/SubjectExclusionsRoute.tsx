import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import { excludeFromSubjects, restoreToSubjects, type SubjectExclusionBanResponse } from "@/api/client";
import { SUBJECT_SUGGESTIONS_PAGE_SIZE, queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { LedgerList } from "@/components/ui/LedgerList";
import { PageBody } from "@/components/layout/PageBody";
import { useCopy } from "@/i18n/context";
import { Trans } from "@/i18n/trans";
import { ACTION } from "@/lib/copy";
import { descricoes, formatCount } from "@/lib/format";
import { SIGNAL_HINT, SIGNAL_LABEL } from "@/lib/quality";
import { routeMessage } from "@/lib/messages";
import { asString } from "@/lib/search";
import { useDebounced } from "@/lib/useDebounced";

/**
 * The curated half of ``NENHUMA``: "this is not a subject at all".
 *
 * The deterministic guard catches what has a *shape* — a date, a placeholder, a street name, a bare
 * number — and on real measurement it caught **1 of 4** of the hand-labelled non-subjects. The rest
 * are semantic calls no rule resolves: ``pessoas`` reaches 166 documents, ``vista aérea`` 89 and
 * ``capanema`` 91. Those are the cases this screen exists for.
 *
 * Confirming a term is **one statement in two halves** (ADR 0013, issue #84): the classifier stops
 * guessing at it, and its spelling is banned from becoming a tag again, so the next ingestion does
 * not recreate the term and park it in the queue forever. The ban deletes nothing — the tag stays in
 * the collection and reachable by search, and excluding the tags with that name is a separate,
 * previewed step on the blocked-spellings screen (``/assuntos/grafias``, #232). A term whose tag
 * already sits in a subject **drawer** is refused and named
 * instead (issue #83, option C): that drawer is a human verdict, and the write that settles a tag is
 * the tag catalogue's ``PATCH``. Since #175 that refusal is read **before** the click: the box asks
 * the preview route as it settles, so the drawer is named while the archivist can still change the
 * term, and the answer the write returns only confirms it.
 */

/** The terms the box holds: the write and the preview split it the same way, or they disagree. */
function draftWords(draft: string): string[] {
  return draft
    .split(/[,\n]/)
    .map((word) => word.trim())
    .filter(Boolean);
}

const routeApi = getRouteApi("/assuntos/excecoes");

/**
 * One search key, and it exists for a link and not for the address bar.
 *
 * The blocked-spellings screen sends the archivist to the verdict that planted a ban, and it sends
 * the term with it: landing on two hundred rows to find one would make the link useless.
 */
export type SubjectExclusionsSearch = { termo?: string };

export function validateSubjectExclusionsSearch(search: Record<string, unknown>): SubjectExclusionsSearch {
  return { termo: asString(search.termo) };
}

export function SubjectExclusionsRoute() {
  const queryClient = useQueryClient();
  const copy = useCopy();
  const search = routeApi.useSearch();
  const exclusions = useQuery(queries.subjectExclusions());
  const [showRecorded, setShowRecorded] = useState(false);
  const [offset, setOffset] = useState(0);
  const suggestions = useQuery(queries.subjectExclusionSuggestions(showRecorded, offset));

  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");
  /** The last write, kept so the screen can name what it refused instead of only counting. */
  const [report, setReport] = useState<SubjectExclusionBanResponse | null>(null);

  const draftTerms = draftWords(draft);
  const settledDraft = useDebounced(draft);
  const preview = useQuery(queries.subjectExclusionPreview(draftWords(settledDraft)));
  /**
   * The plan belongs to the terms in the box: the preview settles 250 ms behind the typing, and a
   * refusal computed for a prefix would name a word the archivist already changed.
   */
  const plan = settledDraft === draft && !preview.isFetching ? preview.data : undefined;
  const blocked = plan?.blocked ?? [];
  const applicable = plan?.applicable ?? [];
  const allBlocked = blocked.length > 0 && applicable.length === 0;

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "subject-exclusions"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "subject-exclusion-suggestions"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "stopwords"] });
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
    onSuccess: (result) => {
      setReport(result);
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

  /**
   * The ledger a `?termo=` link points at, and the reason it is scrolled to.
   *
   * The screen opens with ~1,500 rule candidates and the decision list below them; the blocked-
   * spellings screen sends the archivist here for one term, and a link that lands above a thousand
   * irrelevant rows is a link that does not land. The candidates load in their own request, so the
   * effect waits for it to settle: scrolling before them lands on a page that is about to grow, and
   * the row ends up a thousand pixels lower than the one that was measured. The scroll happens once
   * per term, so restoring a ban does not throw the page back down while the archivist is reading.
   */
  const ledgerRef = useRef<HTMLDivElement | null>(null);
  const scrolledTo = useRef<string | null>(null);
  useEffect(() => {
    if (!search.termo || words.length === 0 || suggestions.isPending) return;
    if (scrolledTo.current === search.termo) return;
    scrolledTo.current = search.termo;
    ledgerRef.current?.scrollIntoView({ block: "start" });
  }, [search.termo, words.length, suggestions.isPending]);

  return (
    <>
      <PageHeader
        screen="subjectExclusions"
        pending={exclusions.isPending}
        status={exclusions.data ? `${formatCount(words.length)} termos fora do eixo de assunto` : undefined}
        actions={
          /*
            The reciprocal of the blocked-spellings screen's notice: this is the screen that says a
            term is not a subject, and the one place that deletes the tags is a different screen.
            A button and not a sentence, because the header has one line and the subtitle already
            says what this screen alone does.
          */
          <Link to="/assuntos/grafias">
            <Button size="sm">{copy.screens.blockedSpellings.label}</Button>
          </Link>
        }
      />

      <PageBody>
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
                <span className="text-sm font-semibold">A regra já recusa estes termos</span>
                <span className="text-xs text-(--color-muted)">
                  {formatCount(suggestions.data.candidate_count)} candidatos ·{" "}
                  {Object.entries(suggestions.data.by_signal ?? {})
                    .map(([signal, count]) => `${SIGNAL_LABEL[signal] ?? signal} ${formatCount(count)}`)
                    .join(" · ")}
                  {suggestions.data.place_count > 0
                    ? ` · ${formatCount(suggestions.data.place_count)} são lugares (o eixo de entidades os carrega)`
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
                  title="Registra de uma vez todos os candidatos que a regra recusa."
                  onClick={() =>
                    ban.mutate({
                      words: (suggestions.data?.items ?? [])
                        .filter((item) => !item.already_excluded)
                        .map((item) => item.term),
                      source: "RULE",
                      reason: "forma reconhecida por regra (ano, placeholder, medida, logradouro ou nome de pessoa)",
                    })
                  }
                >
                  registrar os {formatCount(suggestions.data.candidate_count)} candidatos
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
                            <Badge tone="accent" title="A regra recusa como assunto, mas é um lugar: quem o carrega é o eixo de entidades. Recusar como assunto não exclui o termo.">
                              é lugar
                            </Badge>
                          ) : null}
                          {item.also_an_entity ? (
                            <Badge tone="ok" title="A mesma grafia existe como entidade nomeada: isso é a tela de conflitos, não esta.">
                              também é entidade
                            </Badge>
                          ) : null}
                          {item.macro_category_name ? (
                            <Badge
                              tone="danger"
                              title="Esta tag já está numa categoria de assunto: o registro é recusado aqui. Tire-a da categoria na aba Classificar."
                            >
                              está em {item.macro_category_name}
                            </Badge>
                          ) : null}
                          {item.already_banned ? (
                            <Badge tone="neutral" title="A grafia já está banida de voltar a virar tag.">
                              grafia banida
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
                        disabled={item.already_excluded || Boolean(item.macro_category_name) || ban.isPending}
                        title={
                          item.macro_category_name
                            ? `Está em ${item.macro_category_name}: tire a tag da categoria na aba Classificar antes.`
                            : "O classificador para de adivinhar e a grafia não volta a virar tag."
                        }
                        onClick={() =>
                          ban.mutate({
                            words: [item.term],
                            source: "RULE",
                            reason: `forma reconhecida por regra: ${item.signal}`,
                          })
                        }
                      >
                        Marcar como não-assunto
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
              Os casos que nenhuma regra pega não são sugeridos aqui de propósito — só uma decisão
              humana os registra. Entre eles: <code>pessoas</code>, <code>vista aérea</code> e <code>capanema</code>.
            </p>
          </section>
        ) : null}

        {suggestions.error ? <ErrorState error={suggestions.error} /> : null}
        {suggestions.isPending ? <Spinner label="Conferindo o vocabulário do acervo…" /> : null}

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
                Marcar como não-assunto não exclui nada: a tag continua no acervo, a classificação de
                assunto para de adivinhar e a grafia não volta a virar tag.{" "}
                <Trans
                  text={copy.spellings.verdictDeleteHint}
                  values={{
                    blocked: (
                      <Link
                        to="/assuntos/grafias"
                        className="font-medium underline underline-offset-2"
                      >
                        {copy.screens.blockedSpellings.label}
                      </Link>
                    ),
                  }}
                />
              </span>
            </div>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-(--color-muted)">
              Para os termos que <strong>nenhuma regra alcança</strong> — os julgamentos semânticos. Os
              que a regra já recusa estão na lista acima e entram por ela, com o motivo declarado.
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
            {preview.isError ? <ErrorState error={preview.error} /> : null}
            {blocked.length > 0 ? (
              <p className="text-xs text-(--color-danger)">
                {formatCount(blocked.length)} termo(s) já estão numa categoria de assunto e não serão
                registrados:{" "}
                {blocked
                  .map((item) => `${item.term} (${item.macro_category_name ?? `#${item.macro_category_id}`})`)
                  .join(", ")}
                . Tire a tag da categoria na aba Classificar e volte aqui.
              </p>
            ) : null}
            {applicable.length > 0 ? (
              <p className="text-xs text-(--color-muted)">
                {formatCount(applicable.length)} termo(s) serão registrados e banidos de voltar a virar tag.
              </p>
            ) : null}
            <div>
              <Button
                variant="primary"
                disabled={draftTerms.length === 0 || ban.isPending || allBlocked}
                onClick={() =>
                  ban.mutate({
                    words: draftTerms,
                    reason: reason.trim() || null,
                    source: "HUMAN",
                  })
                }
              >
                {ban.isPending ? "Registrando…" : "Marcar como não-assunto"}
              </Button>
            </div>
            {ban.error ? <ErrorState error={ban.error} /> : null}
            {report ? (
              <div className="grid gap-1 text-xs text-(--color-muted)">
                <span>
                  {routeMessage(report)} {formatCount(report.created)} termo(s) registrado(s),{" "}
                  {formatCount(report.banned)} grafia(s) banida(s) de voltar.
                </span>
                {(report.blocked ?? []).length > 0 ? (
                  <span className="text-(--color-danger)">
                    {formatCount((report.blocked ?? []).length)} recusado(s) por já estar numa categoria de assunto:{" "}
                    {(report.blocked ?? [])
                      .map((item) => `${item.term} (${item.macro_category_name ?? `#${item.macro_category_id}`})`)
                      .join(", ")}
                    . Tire a tag da categoria na aba Classificar e volte aqui.
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        </Disclosure>


        {exclusions.data && words.length === 0 ? (
          <EmptyState
            title="Nenhum termo fora do eixo de assunto"
            hint="A lista nasce vazia: é feita de decisões humanas sobre os casos que nenhuma regra pega. Enquanto o classificador não rodar no acervo, também não há erro a corrigir."
          />
        ) : null}

        {words.length > 0 ? (
          <div ref={ledgerRef}>
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
                  initialTerm={search.termo}
                  renderItem={(word) => (
                    <div className="flex items-center justify-between gap-3 py-1.5">
                      <span className="truncate">{word}</span>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={restore.isPending}
                        title="O classificador volta a considerar o termo, e a grafia volta a poder virar tag. Só o banimento que esta decisão criou sai; uma grafia banida em Grafias bloqueadas continua."
                        onClick={() => restore.mutate(word)}
                      >
                        {ACTION.remove.label}
                      </Button>
                    </div>
                  )}
                />
              </CardBody>
            </Card>
          </div>
        ) : null}

        {restore.error ? <ErrorState error={restore.error} /> : null}

      </PageBody>
    </>
  );
}

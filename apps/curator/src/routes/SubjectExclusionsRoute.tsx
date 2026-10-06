import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { excludeFromSubjects, restoreToSubjects } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { formatCount } from "@/lib/format";

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

  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "subject-exclusions"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const ban = useMutation({
    mutationFn: () =>
      excludeFromSubjects({
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

  const restore = useMutation({
    mutationFn: (word: string) => restoreToSubjects({ words: [word] }),
    onSuccess: invalidate,
  });

  const words = exclusions.data ?? [];

  return (
    <>
      <PageHeader
        title="Não é assunto"
        subtitle={
          exclusions.data ? `${formatCount(words.length)} termos fora do eixo de assunto` : "Lendo as exclusões…"
        }
        actions={
          <Link to="/assuntos/tags">
            <Button size="sm">Vocabulário de tags</Button>
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

        <p className="text-xs text-(--color-muted)">
          Exemplos medidos que pertencem a esta lista: <code>pessoas</code> (166 documentos),{" "}
          <code>vista aérea</code> (89) e <code>capanema</code> (91) — nomes e descrições que o
          classificador não tem como recusar sozinho.
        </p>

        {exclusions.error ? <ErrorState error={exclusions.error} /> : null}
        {exclusions.isPending ? <Spinner /> : null}

        {exclusions.data && words.length === 0 ? (
          <EmptyState
            title="Nenhum termo excluído do eixo de assunto"
            hint="A lista nasce vazia: ela é feita de decisões humanas sobre casos que a regra não pega. Enquanto o classificador não rodar no acervo, também não há erro a corrigir."
          />
        ) : null}

        {words.length > 0 ? (
          <Card>
            <CardHeader className="text-sm font-semibold">Termos vetados</CardHeader>
            <CardBody className="flex flex-wrap gap-2">
              {words.map((word) => (
                <span
                  key={word}
                  className="inline-flex items-center gap-1 rounded-full bg-black/5 py-0.5 pr-1 pl-2 text-xs"
                >
                  {word}
                  <button
                    title="O classificador volta a considerar o termo"
                    disabled={restore.isPending}
                    onClick={() => restore.mutate(word)}
                    className="grid size-5 place-items-center rounded-full text-(--color-muted) hover:bg-black/10 hover:text-(--color-ink)"
                  >
                    ×
                  </button>
                </span>
              ))}
            </CardBody>
          </Card>
        ) : null}

        {restore.error ? <ErrorState error={restore.error} /> : null}

        <Card>
          <CardHeader className="text-sm font-semibold">Vetar termos</CardHeader>
          <CardBody className="grid gap-2">
            <div className="flex flex-wrap gap-1">
              {["pessoas", "vista aérea", "capanema"].map((example) => (
                <button
                  key={example}
                  className="rounded-full bg-black/5 px-2 py-0.5 text-[11px] hover:bg-black/10"
                  title="Preenche o campo com este exemplo medido"
                  onClick={() => setDraft((current) => (current ? `${current}, ${example}` : example))}
                >
                  + {example}
                </button>
              ))}
            </div>
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
                onClick={() => ban.mutate()}
              >
                {ban.isPending ? "Vetando…" : "Marcar como não-assunto"}
              </Button>
            </div>
            {ban.data ? (
              <p className="text-xs text-(--color-muted)">
                {ban.data.message} {formatCount(ban.data.created)} termo(s) registrado(s).
              </p>
            ) : null}
            {ban.error ? <ErrorState error={ban.error} /> : null}
          </CardBody>
        </Card>
      </div>
    </>
  );
}

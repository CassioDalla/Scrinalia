import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { resolveConflict, type ConflictWinner } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { CONFLICT_WINNER_HINT, CONFLICT_WINNER_LABEL, CONFLICT_WINNER_TONE, ENTITY_TYPE_LABEL } from "@/lib/entities";
import { formatCount } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";
import { asNumber } from "@/lib/search";

const routeApi = getRouteApi("/entidades/conflitos");

export type ConflictsSearch = { limiar?: number };

/** How many collision cards the screen draws before it asks the archivist to want more. */
const WINDOW = 50;

export function validateConflictsSearch(search: Record<string, unknown>): ConflictsSearch {
  const limiar = asNumber(search.limiar);
  return { limiar: limiar !== undefined && limiar > 0 && limiar <= 1 ? limiar : undefined };
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
 * What this route does **not** carry is the conflict judge's own verdict — it lists the collisions,
 * not the auto-resolutions. The screen says so instead of inventing a confidence it cannot show.
 */
export function ConflictsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const threshold = search.limiar ?? 0.85;
  const conflicts = useQuery(queries.crossDomainConflicts(threshold));

  const [lastResolution, setLastResolution] = useState<string | null>(null);

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

  const applyThreshold = () => {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 1) {
      setDraft(String(threshold));
      return;
    }
    navigate({ to: "/entidades/conflitos", search: { limiar: parsed } });
  };

  /**
   * The route answers every collision at once — 2.502 of them on the real vocabulary — so the screen
   * draws a window and grows it on demand. Rendering thousands of cards at once is what makes a
   * screen feel broken, and there is no paging parameter to lean on.
   */
  const [visible, setVisible] = useState(WINDOW);

  const resolve = useMutation({
    mutationFn: (body: { tag_id: number; entity_id: number; winner: ConflictWinner }) => resolveConflict(body),
    onSuccess: (response) => {
      setLastResolution(response.message);
      void queryClient.invalidateQueries({ queryKey: ["taxonomy", "conflicts"] });
      void queryClient.invalidateQueries({ queryKey: ["taxonomy", "stopwords"] });
      void queryClient.invalidateQueries({ queryKey: ["taxonomy", "ner-exclusions"] });
      void queryClient.invalidateQueries({ queryKey: ["taxonomy", "entities"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    },
  });

  const rows = conflicts.data?.data ?? [];
  const shown = rows.slice(0, visible);

  return (
    <>
      <PageHeader
        title="Conflitos entre assunto e nome próprio"
        subtitle={
          conflicts.data
            ? `${formatCount(rows.length)} colisões acima de ${threshold.toFixed(2)} de similaridade de trigrama`
            : "Comparando os vocabulários…"
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        {/*
          The explanation collapses; the queue does not.
          
          This block is read once and then permanent — every visit re-rendered four lines of governance
          above the work. The consequence of each verdict is repeated on the button that takes it, which
          is where it is actually needed; the paragraph stays here as the long version.
        */}
        <Disclosure
          toggleLabel="Onde cada veredito é gravado"
          header={
            <div className="grid gap-1">
              <span className="text-sm font-semibold">Onde cada veredito é gravado</span>
              <span className="text-xs text-(--color-muted)">
                tag vence: {CONFLICT_WINNER_HINT.TAG} · entidade vence: {CONFLICT_WINNER_HINT.ENTITY}
              </span>
            </div>
          }
        >
          <p className="text-xs text-(--color-accent)">
            A decisão é guardada em <strong>dois lugares diferentes</strong>, de propósito: não são o
            mesmo mecanismo — e um veto de entidade não pode fazer a purga de assunto apagar uma tag
            que você manteve.
          </p>
        </Disclosure>

        <div className="flex flex-wrap items-end justify-between gap-3">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Limiar de similaridade</span>
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
          </label>
          <p className="text-xs text-(--color-muted)">
            A varredura ao vivo é medida em segundos no vocabulário real; abaixo do limiar os pares
            deixam de ser notícia.
          </p>
        </div>

        {conflicts.error ? <ErrorState error={conflicts.error} /> : null}
        {conflicts.isPending ? <Spinner label="Cruzando tags e entidades…" /> : null}

        {conflicts.data && rows.length === 0 ? (
          <EmptyState
            title="Nenhuma colisão acima do limiar"
            hint="Nenhuma tag e nenhum nome próprio compartilham a mesma grafia neste limiar. Baixar o limiar mostra pares mais frouxos — e mais falsos positivos."
          />
        ) : null}

        {lastResolution ? (
          <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/20">
            {lastResolution}
          </p>
        ) : null}
        {resolve.error ? <ErrorState error={resolve.error} /> : null}

        <ul className="grid gap-2">
          {shown.map((row) => (
            <li key={`${row.tag_id}-${row.entity_id}`}>
              {/*
                The verdict sits on the collapsed row, next to the collision it decides: the archivist
                reads "isto é a mesma grafia" and answers it in one click, without opening anything. The
                body keeps the evidence — the ids and what each verdict writes.
              */}
              <Disclosure
                toggleLabel="Ver a evidência e o que cada veredito grava"
                header={
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="flex min-w-0 items-center gap-2">
                      <Badge tone="accent">assunto</Badge>
                      <span className="truncate text-sm font-medium">{row.tag_name}</span>
                      <code className="text-[10px] text-(--color-muted)">#{row.tag_id}</code>
                    </span>
                    <span className="text-(--color-muted)">≈ {row.similarity.toFixed(3)} ≈</span>
                    <span className="flex min-w-0 items-center gap-2">
                      <Badge tone="ok">{labelOf(ENTITY_TYPE_LABEL, row.entity_type)}</Badge>
                      <span className="truncate text-sm font-medium">{row.entity_name}</span>
                      <code className="text-[10px] text-(--color-muted)">#{row.entity_id}</code>
                    </span>
                  </div>
                }
                actions={
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={resolve.isPending}
                      title={CONFLICT_WINNER_HINT.TAG}
                      onClick={() =>
                        resolve.mutate({ tag_id: row.tag_id, entity_id: row.entity_id, winner: "TAG" })
                      }
                    >
                      <Badge tone={CONFLICT_WINNER_TONE.TAG}>{CONFLICT_WINNER_LABEL.TAG}</Badge> vence
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={resolve.isPending}
                      title={CONFLICT_WINNER_HINT.ENTITY}
                      onClick={() =>
                        resolve.mutate({ tag_id: row.tag_id, entity_id: row.entity_id, winner: "ENTITY" })
                      }
                    >
                      <Badge tone={CONFLICT_WINNER_TONE.ENTITY}>{CONFLICT_WINNER_LABEL.ENTITY}</Badge> vence
                    </Button>
                  </div>
                }
              >
                <ul className="grid gap-1 text-xs text-(--color-muted)">
                  <li>
                    <strong className="text-(--color-ink)">{CONFLICT_WINNER_LABEL.TAG} vence:</strong>{" "}
                    {CONFLICT_WINNER_HINT.TAG}
                  </li>
                  <li>
                    <strong className="text-(--color-ink)">{CONFLICT_WINNER_LABEL.ENTITY} vence:</strong>{" "}
                    {CONFLICT_WINNER_HINT.ENTITY}
                  </li>
                  <li>
                    par: <code>{row.tag_name}</code> (tag #{row.tag_id}) ≈ <code>{row.entity_name}</code> (
                    {labelOf(ENTITY_TYPE_LABEL, row.entity_type)} #{row.entity_id}) — similaridade{" "}
                    {row.similarity.toFixed(3)}
                  </li>
                </ul>
              </Disclosure>
            </li>
          ))}
        </ul>

        {visible < rows.length ? (
          <Button variant="secondary" onClick={() => setVisible((current) => current + WINDOW)}>
            mostrar mais {formatCount(Math.min(WINDOW, rows.length - visible))} de{" "}
            {formatCount(rows.length - visible)} restantes
          </Button>
        ) : null}

        <p className="text-xs text-(--color-muted)">
          O juiz de conflitos resolve sozinho os casos acima do limiar dele e manda para revisão só os
          duvidosos — é <em>essa</em> fila que a tela inicial conta, e por isso ela é bem menor que esta
          lista. Aqui a varredura é ao vivo: todos os pares acima do limiar, decididos ou não. As
          decisões do juiz aparecem como <em>juiz LLM</em> na lista de exclusões de NER.
        </p>
      </div>
    </>
  );
}

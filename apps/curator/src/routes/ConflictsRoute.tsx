import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  previewConflictResolution,
  resolveConflict,
  undoConflictResolution,
  type ConflictPairKindFilter,
  type ConflictResolutionPlan,
  type ConflictWinner,
} from "@/api/client";
import { CONFLICTS_PAGE_SIZE, queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { ACTION } from "@/lib/copy";
import { CONFLICT_WINNER_HINT, CONFLICT_WINNER_LABEL, CONFLICT_WINNER_TONE, ENTITY_TYPE_LABEL } from "@/lib/entities";
import { formatCount, formatDateTime } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";
import { asNumber } from "@/lib/search";
import { routeMessage } from "@/lib/messages";

const routeApi = getRouteApi("/entidades/conflitos");

export type ConflictsSearch = { limiar?: number; ver?: ConflictView; tipo?: ConflictPairKindFilter; pagina?: number };

/** The three reads this screen makes: the live pairs, the judge's verdicts, and the ledger. */
export type ConflictView = "pendentes" | "decididos" | "resolucoes";

const VIEWS: { key: ConflictView; label: string; hint: string }[] = [
  { key: "pendentes", label: "Pendentes", hint: "O que a varredura ao vivo encontra" },
  { key: "decididos", label: "Decididos pelo juiz", hint: "O que ele já julgou" },
  { key: "resolucoes", label: "Resoluções", hint: "O que foi escrito, e o desfazer" },
];

const PAIR_KINDS: { key: ConflictPairKindFilter; label: string; hint: string }[] = [
  {
    key: "near_duplicate",
    label: "grafias diferentes",
    hint: "A mesma palavra escrita de duas formas — quase sempre abreviação de logradouro. É a pergunta de grafia.",
  },
  {
    key: "exact_name",
    label: "nomes idênticos",
    hint: "A mesma grafia nos dois eixos. É uma pergunta estrutural, e no acervo real são milhares.",
  },
  { key: "all", label: "todos", hint: "Nenhum filtro: as duas populações juntas." },
];

export function validateConflictsSearch(search: Record<string, unknown>): ConflictsSearch {
  const limiar = asNumber(search.limiar);
  const pagina = asNumber(search.pagina);
  const ver = search.ver;
  const tipo = search.tipo;
  return {
    limiar: limiar !== undefined && limiar > 0 && limiar <= 1 ? limiar : undefined,
    ver: ver === "decididos" || ver === "resolucoes" ? ver : undefined,
    tipo: tipo === "exact_name" || tipo === "all" || tipo === "near_duplicate" ? tipo : undefined,
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
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const threshold = search.limiar ?? 0.85;
  const view = search.ver ?? "pendentes";
  const pairKind = search.tipo ?? "near_duplicate";
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

  const conflicts = useQuery(queries.crossDomainConflicts(threshold, pairKind, page));
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

  return (
    <>
      <PageHeader
        screen="conflicts"
        pending={view === "pendentes" ? conflicts.isPending : view === "decididos" ? judged.isPending : ledger.isPending}
        status={
          view === "pendentes" && conflicts.data
            ? `${formatCount(conflicts.data.total)} colisões acima de ${threshold.toFixed(2)} de similaridade de trigrama`
            : view === "decididos" && judged.data
              ? `${formatCount(judged.data.total)} pares julgados · ${formatCount(judged.data.still_applicable)} ainda decidíveis`
              : view === "resolucoes" && ledger.data
                ? `${formatCount(ledger.data.total)} resoluções no ledger`
                : undefined
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
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
            mesmo mecanismo — e um veto de entidade não pode fazer a purga de assunto excluir uma tag que
            você manteve. Toda resolução agora deixa também uma linha no ledger, com o que foi
            transferido e qual bloqueio foi plantado, e é isso que torna o desfazer exato.
          </p>
        </Disclosure>

        {/* The three reads are tabs, not filters: they are different questions about different data. */}
        <div className="flex flex-wrap gap-2">
          {VIEWS.map((item) => (
            <Button
              key={item.key}
              size="sm"
              variant={view === item.key ? "primary" : "secondary"}
              title={item.hint}
              onClick={() => goTo({ ver: item.key === "pendentes" ? undefined : item.key })}
            >
              {item.label}
            </Button>
          ))}
        </div>

        {view === "pendentes" ? (
          <>
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
              {conflicts.data ? (
                <p className="text-xs text-(--color-muted)">
                  {formatCount(conflicts.data.near_duplicate_count)} grafias diferentes ·{" "}
                  {formatCount(conflicts.data.exact_name_count)} nomes idênticos ·{" "}
                  {formatCount(conflicts.data.judged_count)} já com veredito
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
              {PAIR_KINDS.map((kind) => (
                <Button
                  key={kind.key}
                  size="sm"
                  variant={pairKind === kind.key ? "primary" : "ghost"}
                  title={kind.hint}
                  onClick={() => goTo({ tipo: kind.key === "near_duplicate" ? undefined : kind.key })}
                >
                  {kind.label}
                </Button>
              ))}
            </div>
          </>
        ) : null}

        {feedback ? (
          <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/20">
            {feedback}
          </p>
        ) : null}
        {active.error ? <ErrorState error={active.error} /> : null}
        {active.isPending ? <Spinner label="Lendo a colisão…" /> : null}
        {resolve.error ? <ErrorState error={resolve.error} /> : null}
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
                title="Nenhuma colisão nesta população"
                hint="Nenhuma tag e nenhum nome próprio se parecem o bastante neste limiar. Baixar o limiar mostra pares mais frouxos — e mais falsos positivos."
              />
            ) : null}
            <ul className="grid gap-2">
              {(conflicts.data?.items ?? []).map((row) => (
                <li key={`${row.tag_id}-${row.entity_id}`}>
                  <Card>
                    <CardBody className="grid gap-2">
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
                        <Badge tone={row.pair_kind === "EXACT_NAME" ? "neutral" : "warn"}>
                          {row.pair_kind === "EXACT_NAME" ? "mesma grafia" : "grafia parecida"}
                        </Badge>
                        {row.judge_winner ? (
                          <Badge tone={CONFLICT_WINNER_TONE[row.judge_winner]}>
                            juiz: {CONFLICT_WINNER_LABEL[row.judge_winner]}
                            {row.judge_confidence != null ? ` (${row.judge_confidence.toFixed(2)})` : ""}
                          </Badge>
                        ) : null}
                      </div>
                      {row.judge_reason ? (
                        <p className="text-xs text-(--color-muted)">Juiz: {row.judge_reason}</p>
                      ) : null}
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={ask.isPending}
                          title="Mostra o que cada veredito transfere, exclui e bloqueia. Nada é escrito."
                          onClick={() => ask.mutate({ tag_id: row.tag_id, entity_id: row.entity_id })}
                        >
                          ver o impacto antes de decidir
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
            title="O juiz ainda não julgou nada"
            hint="O worker conflict-judge é quem escreve aqui. Uma fila vazia quer dizer que ele não rodou, não que não há colisão — a aba Pendentes é a que mostra o que existe hoje."
          />
        ) : null}

        {view === "decididos" && judged.data ? (
          <>
            <div className="flex flex-wrap gap-2 text-xs text-(--color-muted)">
              <Badge tone="ok">{formatCount(judged.data.auto_resolved)} auto-resolvidas</Badge>
              <Badge tone="warn">{formatCount(judged.data.sent_to_human)} foram para revisão humana</Badge>
              <Badge tone="accent">{formatCount(judged.data.tag_wins)} a favor do assunto</Badge>
              <Badge tone="neutral">{formatCount(judged.data.entity_wins)} a favor da entidade</Badge>
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
                          {item.judge_winner ? CONFLICT_WINNER_LABEL[item.judge_winner] : "sem veredito"}
                        </Badge>
                        {item.judge_confidence != null ? (
                          <Badge tone="neutral">{item.judge_confidence.toFixed(2)}</Badge>
                        ) : null}
                        <Badge tone={item.judge_status === "AI_APPROVED" ? "ok" : "warn"}>
                          {item.judge_status === "AI_APPROVED" ? "auto-resolvida" : "revisão humana"}
                        </Badge>
                        {item.applicable ? <Badge tone="accent">ainda decidível</Badge> : null}
                      </div>
                      {item.judge_reason ? <p className="text-xs text-(--color-muted)">{item.judge_reason}</p> : null}
                      <p className="text-xs text-(--color-muted)">
                        {item.tag_alive ? "tag viva" : "tag já removida"} ·{" "}
                        {item.entity_alive ? "entidade viva" : "entidade já removida"} — a linha do juiz
                        sobrevive ao vocabulário que ela nomeia, e é por isso que ela é lida aqui e não na
                        varredura.
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
            title="Nenhuma resolução escrita"
            hint="Toda decisão — do juiz ou da curadoria — deixa uma linha aqui, com o que foi transferido e qual bloqueio foi plantado. É essa linha que torna o desfazer exato."
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
                        venceu: {CONFLICT_WINNER_LABEL[entry.winner]}
                      </Badge>
                      <Badge tone={entry.source === "JUDGE" ? "accent" : "ok"}>
                        {entry.source === "JUDGE" ? "juiz LLM" : "curadoria"}
                      </Badge>
                      {entry.is_undone ? <Badge tone="neutral">desfeita</Badge> : null}
                    </div>
                    <p className="text-xs text-(--color-muted)">
                      {formatCount(entry.documents_transferred)} vínculo(s) criado(s)
                      {entry.ban_kind ? (
                        <>
                          {" "}
                          · bloqueio <code>{entry.ban_kind}</code> em <code>{entry.ban_term}</code>
                          {entry.ban_created ? " (plantado por esta resolução)" : " (já existia)"}
                        </>
                      ) : null}
                      {entry.decided_by ? ` · por ${entry.decided_by}` : ""}
                      {entry.decided_at ? ` em ${formatDateTime(entry.decided_at)}` : ""}
                    </p>
                    {entry.note ? <p className="text-xs text-(--color-muted)">Nota: {entry.note}</p> : null}
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={entry.is_undone || undo.isPending}
                        title={
                          entry.is_undone
                            ? "Esta resolução já foi desfeita; o ledger guarda a história."
                            : "Devolve a linha removida, os vínculos e o bloqueio que esta resolução plantou."
                        }
                        onClick={() => undo.mutate(entry.resolution_id)}
                      >
                        {ACTION.undo.label}
                      </Button>
                      {entry.is_undone ? (
                        <span className="text-xs text-(--color-muted)">
                          desfeita{entry.undone_by ? ` por ${entry.undone_by}` : ""}
                          {entry.loser_restored ? " · linha restaurada" : " · linha não restaurada"}
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
              ← Anterior
            </Button>
            <span className="text-xs text-(--color-muted)">
              página {formatCount(page + 1)} de {formatCount(lastPage)} · {formatCount(total)} no total
            </span>
            <Button
              size="sm"
              disabled={(page + 1) * CONFLICTS_PAGE_SIZE >= total}
              onClick={() => navigate({ to: "/entidades/conflitos", search: { ...search, pagina: page + 1 } })}
            >
              Próxima →
            </Button>
          </div>
        ) : null}

        <p className="text-xs text-(--color-muted)">
          O juiz de conflitos resolve sozinho os casos acima do limiar dele e manda para revisão só os
          duvidosos — é <em>essa</em> fila que a tela inicial conta. A aba <em>decididos</em> é a única
          que mostra as auto-resoluções: elas excluíram a linha perdedora, então não existem mais na
          varredura ao vivo.
        </p>
      </div>
    </>
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
  return (
    <Card className="ring-2 ring-(--color-accent)/30">
      <CardBody className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">Impacto antes de decidir</span>
          <Badge tone="accent">assunto: {plan.tag_name}</Badge>
          <Badge tone="ok">
            {labelOf(ENTITY_TYPE_LABEL, plan.entity_type)}: {plan.entity_name}
          </Badge>
          <Badge tone="neutral">similaridade {plan.similarity.toFixed(3)}</Badge>
        </div>

        {plan.already_resolved ? (
          <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/25">
            Este par já tem uma resolução em vigor no ledger. Decidir de novo escreve uma segunda
            resolução — o desfazer de cada uma é independente.
          </p>
        ) : null}

        {plan.judge_winner ? (
          <p className="text-xs text-(--color-muted)">
            O juiz já opinou: <strong>{CONFLICT_WINNER_LABEL[plan.judge_winner]}</strong>
            {plan.judge_confidence != null ? ` com ${plan.judge_confidence.toFixed(2)} de confiança` : ""}
            {plan.judge_reason ? ` — ${plan.judge_reason}` : ""}.
          </p>
        ) : null}

        {!plan.resolvable ? (
          <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/25">
            {plan.blocker}
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            <VerdictCard
              title={`${CONFLICT_WINNER_LABEL.TAG} vence`}
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
              title={`${CONFLICT_WINNER_LABEL.ENTITY} vence`}
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
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nota da decisão</span>
            <Input value={note} onChange={(event) => onNote(event.target.value)} />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            disabled={pending || !plan.resolvable || !plan.tag_alive || !plan.entity_alive}
            title={CONFLICT_WINNER_HINT.TAG}
            onClick={() => onConfirm("TAG")}
          >
            {ACTION.apply.label}: {CONFLICT_WINNER_LABEL.TAG} vence
          </Button>
          <Button
            variant="primary"
            disabled={pending || !plan.resolvable || !plan.tag_alive || !plan.entity_alive}
            title={CONFLICT_WINNER_HINT.ENTITY}
            onClick={() => onConfirm("ENTITY")}
          >
            {ACTION.apply.label}: {CONFLICT_WINNER_LABEL.ENTITY} vence
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
  return (
    <div className="grid gap-1 rounded-md bg-black/[0.02] px-3 py-2 text-xs ring-1 ring-(--color-line)">
      <Badge tone={tone}>{title}</Badge>
      <p className="text-(--color-muted)">
        <strong className="text-(--color-ink)">{formatCount(transferred)}</strong> vínculo(s) novo(s)
        {alreadyLinked > 0 ? ` · ${formatCount(alreadyLinked)} documento(s) já tinham este lado` : ""}
      </p>
      {loses ? (
        <p className="text-(--color-muted)">
          desaparece: <code>{loses}</code>
        </p>
      ) : null}
      {banTerm ? (
        <p className="text-(--color-muted)">
          bloqueio <code>{banKind}</code> em <code>{banTerm}</code>
          {banExists ? " — já existe, não é reescrito" : " — será plantado por esta decisão"}
        </p>
      ) : null}
      <p className="text-(--color-muted)">{hint}</p>
    </div>
  );
}

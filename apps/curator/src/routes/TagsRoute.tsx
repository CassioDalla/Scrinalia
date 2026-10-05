import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  applyMergeBatch,
  decideMergeProposal,
  previewMerge,
  suggestMergeProposals,
  undoMerge,
  type BatchMergeResponse,
  type MergePreview,
  type ProposalStatus,
  type TagMergeProposal,
  type TagPairSimilarity,
} from "@/api/client";
import { queries, MERGE_LOG_PAGE_SIZE, PROPOSALS_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { formatCount, formatDateTime } from "@/lib/format";
import {
  MERGE_REASON_LABEL,
  MERGE_REASON_TONE,
  PROPOSAL_STATUS_LABEL,
  PROPOSAL_STATUS_TONE,
  REVIEW_FLAG_HINT,
  REVIEW_FLAG_LABEL,
  labelOf,
} from "@/lib/taxonomy";

const routeApi = getRouteApi("/assuntos/tags");

const TABS = [
  { id: "relevancia", label: "Relevância" },
  { id: "similaridade", label: "Similaridade" },
  { id: "propostas", label: "Propostas de merge" },
];

const REASONS = ["TRIGRAM", "PLURAL", "MIXED"];
const STATUSES: ProposalStatus[] = ["SUGGESTED", "APPROVED", "REJECTED"];

export type TagsSearch = {
  aba?: string;
  metodo?: "count" | "tfidf";
  limiar?: number;
  alvo?: string;
  nome?: string;
  status?: ProposalStatus;
  motivo?: string;
  min?: number;
  flag?: boolean;
  offset?: number;
};

function asNumber(value: unknown): number | undefined {
  const parsed = typeof value === "string" ? Number(value) : undefined;
  return parsed !== undefined && Number.isFinite(parsed) ? parsed : undefined;
}

export function validateTagsSearch(search: Record<string, unknown>): TagsSearch {
  const status = search.status;
  const metodo = search.metodo;
  const aba = search.aba;
  return {
    aba: typeof aba === "string" && TABS.some((tab) => tab.id === aba) ? aba : "relevancia",
    metodo: metodo === "tfidf" ? "tfidf" : "count",
    limiar: asNumber(search.limiar) ?? 0.65,
    alvo: typeof search.alvo === "string" && search.alvo.length > 0 ? search.alvo : undefined,
    nome: typeof search.nome === "string" && search.nome.length > 0 ? search.nome : undefined,
    status:
      typeof status === "string" && (STATUSES as string[]).includes(status) ? (status as ProposalStatus) : undefined,
    motivo: typeof search.motivo === "string" && REASONS.includes(search.motivo) ? search.motivo : undefined,
    min: asNumber(search.min),
    flag: search.flag === true || search.flag === "true" ? true : undefined,
    offset: asNumber(search.offset),
  };
}

/**
 * The tag catalog: what weighs most, what looks duplicated, and the queue of merge decisions.
 *
 * The three questions live in one route because they are one conversation — the archivist sees that
 * ``alvenarias`` weighs little, finds its near-duplicate, and decides whether to absorb it. The
 * active question is in the URL, so a colleague can be sent the exact list.
 *
 * The fourth subtab of the sitemap (stopwords) is **not** here, and the screen says why instead of
 * offering a button that would delete tags: the purge has no read route for the current stopwords
 * and no preview of what it would remove.
 */
export function TagsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const patch = (changes: Partial<TagsSearch>) =>
    navigate({ to: "/assuntos/tags", search: { ...search, ...changes, offset: undefined } });

  return (
    <>
      <PageHeader
        title="Vocabulário de tags"
        subtitle="Peso, duplicatas e a fila de merges — a decisão é sempre sua, e o merge é reversível."
      />

      <div className="px-6">
        <Tabs
          items={TABS}
          active={search.aba ?? "relevancia"}
          onChange={(id) => patch({ aba: id })}
        />
      </div>

      <div className="px-6 py-5">
        {search.aba === "similaridade" ? (
          <SimilarityTab search={search} patch={patch} />
        ) : search.aba === "propostas" ? (
          <ProposalsTab search={search} patch={patch} />
        ) : (
          <RelevanceTab search={search} patch={patch} />
        )}
      </div>
    </>
  );
}

// =============================================================================================
// Relevância
// =============================================================================================

function RelevanceTab({
  search,
  patch,
}: {
  search: TagsSearch;
  patch: (changes: Partial<TagsSearch>) => void;
}) {
  const method = search.metodo ?? "count";
  const [limit, setLimit] = useState(30);
  const relevance = useQuery(queries.tagRelevance(method, limit));

  const payload = relevance.data?.payload ?? [];

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select className="w-48" value={method} onChange={(event) => patch({ metodo: event.target.value as "count" | "tfidf" })}>
          <option value="count">Contagem de uso</option>
          <option value="tfidf">TF-IDF (pune o genérico)</option>
        </Select>
        <Select className="w-36" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
          {[30, 50, 100, 200].map((value) => (
            <option key={value} value={value}>
              {value} tags
            </option>
          ))}
        </Select>
      </div>

      <p className="max-w-3xl text-xs text-(--color-muted)">
        A contagem mostra o que pesa no acervo; o TF-IDF mostra o que é específico, punindo o que aparece em toda
        parte. As duas listas respondem perguntas diferentes de propósito — a primeira acha o que dominar, a segunda
        o que caracteriza.
      </p>

      {relevance.error ? <ErrorState error={relevance.error} /> : null}
      {relevance.isPending ? <Spinner /> : null}

      {payload.length > 0 ? (
        <Card>
          <CardBody className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-(--color-line) text-xs text-(--color-muted)">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Tag</th>
                  {method === "count" ? (
                    <th className="px-3 py-2 text-right font-medium">Documentos</th>
                  ) : (
                    <>
                      <th className="px-3 py-2 text-right font-medium">Frequência</th>
                      <th className="px-3 py-2 text-right font-medium">IDF</th>
                      <th className="px-3 py-2 text-right font-medium">TF-IDF</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {payload.map((row) => (
                  <tr key={row.name} className="border-b border-(--color-line) last:border-b-0">
                    <td className="px-3 py-1.5">{row.name}</td>
                    {"total_usage" in row ? (
                      <td className="px-3 py-1.5 text-right tabular-nums">{formatCount(row.total_usage)}</td>
                    ) : (
                      <>
                        <td className="px-3 py-1.5 text-right tabular-nums">{formatCount(row.frequency)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{row.weight_idf.toFixed(2)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{row.score_tfidf.toFixed(2)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

// =============================================================================================
// Similaridade
// =============================================================================================

function SimilarityTab({
  search,
  patch,
}: {
  search: TagsSearch;
  patch: (changes: Partial<TagsSearch>) => void;
}) {
  const threshold = search.limiar ?? 0.65;
  const [showAll, setShowAll] = useState(false);
  const similar = useQuery(queries.similarTagPairs(threshold));

  const pairs = (similar.data ?? []).filter(
    (row): row is TagPairSimilarity => "sim_score" in row,
  );
  const term = search.nome?.toLowerCase();
  const visible = pairs.filter((pair) => {
    if (!term) return true;
    return pair.name_1.toLowerCase().includes(term) || pair.name_2.toLowerCase().includes(term);
  });
  const shown = showAll ? visible : visible.slice(0, 100);

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-xs">
          <span className="text-(--color-muted)">limiar</span>
          <Input
            type="number"
            step="0.05"
            min="0.3"
            max="1"
            className="w-24"
            value={threshold}
            onChange={(event) => patch({ limiar: Number(event.target.value) })}
          />
        </label>
        <Input
          className="max-w-xs"
          placeholder="filtrar por nome…"
          defaultValue={search.nome ?? ""}
          onChange={(event) => patch({ nome: event.target.value || undefined })}
        />
      </div>

      <p className="max-w-3xl text-xs text-(--color-muted)">
        Pares por similaridade de trigrama. É a evidência que a proposta de merge usa — mostrada crua, sem julgar:
        <code> 'alameda cabral' </code> e <code> 'al. alameda cabral' </code> têm similaridade 1.000, e nenhum
        limiar distingue sozinho o que é abreviação do que é outra coisa.
      </p>

      {similar.error ? <ErrorState error={similar.error} /> : null}
      {similar.isPending ? <Spinner /> : null}

      {similar.data && pairs.length === 0 ? (
        <EmptyState
          title="Nenhum par acima do limiar"
          hint="Baixe o limiar para ver pares mais distantes, ou rode uma proposta de merge para registrar os clusters."
        />
      ) : null}

      {shown.length > 0 ? (
        <Card>
          <CardHeader className="flex items-center justify-between text-xs text-(--color-muted)">
            <span>
              {formatCount(visible.length)} par(es)
              {term ? ` para “${search.nome}”` : ""} de {formatCount(pairs.length)}
            </span>
          </CardHeader>
          <CardBody className="p-0">
            <ul className="divide-y divide-(--color-line) text-sm">
              {shown.map((pair) => (
                <li key={`${pair.id_1}-${pair.id_2}`} className="flex items-center justify-between gap-3 px-3 py-1.5">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate">{pair.name_1}</span>
                    <span className="text-(--color-muted)">↔</span>
                    <span className="truncate">{pair.name_2}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-(--color-muted)">{pair.sim_score.toFixed(3)}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {!showAll && visible.length > shown.length ? (
        <div>
          <Button size="sm" onClick={() => setShowAll(true)}>
            mostrar os {formatCount(visible.length)} pares
          </Button>
        </div>
      ) : null}
    </div>
  );
}

// =============================================================================================
// Propostas de merge
// =============================================================================================

function ProposalsTab({
  search,
  patch,
}: {
  search: TagsSearch;
  patch: (changes: Partial<TagsSearch>) => void;
}) {
  const queryClient = useQueryClient();
  const [threshold, setThreshold] = useState(0.65);
  const [selected, setSelected] = useState<number[]>([]);
  const [batch, setBatch] = useState<BatchMergeResponse | null>(null);

  const proposals = useQuery(queries.mergeProposals(search));
  const log = useQuery(queries.mergeLog());

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-log"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "tags"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const suggest = useMutation({
    mutationFn: () => suggestMergeProposals({ threshold, limit: 500 }),
    onSuccess: invalidate,
  });

  const apply = useMutation({
    mutationFn: () => applyMergeBatch({ proposal_ids: selected, changed_by: null, note: null }),
    onSuccess: (data) => {
      setBatch(data);
      setSelected([]);
      invalidate();
    },
  });

  const undo = useMutation({
    mutationFn: (mergeId: number) => undoMerge(mergeId),
    onSuccess: invalidate,
  });

  const items = proposals.data?.items ?? [];
  const total = proposals.data?.total ?? 0;
  const offset = search.offset ?? 0;

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
          {suggest.isPending ? "Propondo…" : "Propor clusters"}
        </Button>
        <label className="flex items-center gap-2 text-xs">
          <span className="text-(--color-muted)">limiar</span>
          <Input
            type="number"
            step="0.05"
            min="0.3"
            max="1"
            className="w-24"
            value={threshold}
            onChange={(event) => setThreshold(Number(event.target.value))}
          />
        </label>
        <Select
          className="w-40"
          value={search.status ?? ""}
          onChange={(event) => patch({ status: (event.target.value || undefined) as ProposalStatus | undefined })}
        >
          <option value="">Todos os status</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {labelOf(PROPOSAL_STATUS_LABEL, status)}
            </option>
          ))}
        </Select>
        <Select
          className="w-44"
          value={search.motivo ?? ""}
          onChange={(event) => patch({ motivo: event.target.value || undefined })}
        >
          <option value="">Todo motivo</option>
          {REASONS.map((reason) => (
            <option key={reason} value={reason}>
              {labelOf(MERGE_REASON_LABEL, reason)}
            </option>
          ))}
        </Select>
        <Input
          type="number"
          className="w-32"
          placeholder="mín. docs"
          defaultValue={search.min ?? ""}
          onChange={(event) => patch({ min: event.target.value ? Number(event.target.value) : undefined })}
        />
        <Button
          size="sm"
          variant={search.flag ? "primary" : "secondary"}
          onClick={() => patch({ flag: search.flag ? undefined : true })}
        >
          só com avisos
        </Button>
      </div>

      {suggest.data ? (
        <p className="rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/25">
          Proposta: {formatCount(suggest.data.clusters_found)} cluster(s) encontrados, {formatCount(suggest.data.persisted)}{" "}
          registrados, {formatCount(suggest.data.pending)} pendentes, {formatCount(suggest.data.flagged)} com aviso. Uma
          decisão já tomada não é sobrescrita.
        </p>
      ) : null}
      {suggest.error ? <ErrorState error={suggest.error} /> : null}

      {selected.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-(--color-accent)/5 px-3 py-2 ring-1 ring-(--color-accent)/25">
          <span className="text-xs">
            {formatCount(selected.length)} cluster(s) aprovado(s) selecionado(s)
          </span>
          <Button size="sm" variant="primary" disabled={apply.isPending} onClick={() => apply.mutate()}>
            {apply.isPending ? "Aplicando…" : "Aplicar em lote"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            limpar seleção
          </Button>
        </div>
      ) : null}

      {apply.error ? <ErrorState error={apply.error} /> : null}
      {batch ? (
        <div className="grid gap-1 rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs ring-1 ring-(--color-ok)/25">
          <p className="font-medium text-(--color-ok)">
            {formatCount((batch.applied ?? []).length)} cluster(s) aplicado(s), {formatCount((batch.failed ?? []).length)} falha(s).
          </p>
          {(batch.applied ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-muted)">
              #{entry.proposal_id}: {formatCount(entry.documents_updated)} documento(s), {formatCount(entry.tags_deleted)}{" "}
              tag(s) absorvida(s) · ledger {(entry.merge_ids ?? []).join(", ")}
            </p>
          ))}
          {(batch.failed ?? []).map((entry) => (
            <p key={entry.proposal_id} className="text-(--color-danger)">
              #{entry.proposal_id} não aplicado: {entry.error}
            </p>
          ))}
        </div>
      ) : null}

      {proposals.error ? <ErrorState error={proposals.error} /> : null}
      {proposals.isPending ? (
        <div className="grid gap-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-32" />
          ))}
        </div>
      ) : null}

      {proposals.data && total === 0 ? (
        <EmptyState
          title="Nenhuma proposta com este filtro"
          hint="Rode 'Propor clusters' para registrar os pares acima do limiar. A proposta não unifica nada: ela só escreve a pergunta."
          action={
            <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
              Propor clusters
            </Button>
          }
        />
      ) : null}

      <ul className="grid gap-2">
        {items.map((proposal) => (
          <li key={proposal.proposal_id}>
            <ProposalCard
              proposal={proposal}
              selected={selected.includes(proposal.proposal_id)}
              onToggle={(checked) =>
                setSelected((current) =>
                  checked ? [...current, proposal.proposal_id] : current.filter((id) => id !== proposal.proposal_id),
                )
              }
            />
          </li>
        ))}
      </ul>

      {total > PROPOSALS_PAGE_SIZE ? (
        <div className="flex items-center justify-between text-sm">
          <Button
            size="sm"
            disabled={offset === 0}
            onClick={() => patch({ offset: Math.max(0, offset - PROPOSALS_PAGE_SIZE) })}
          >
            ← Anterior
          </Button>
          <span className="text-xs text-(--color-muted)">
            {formatCount(offset + 1)}–{formatCount(Math.min(offset + PROPOSALS_PAGE_SIZE, total))} de {formatCount(total)}
          </span>
          <Button
            size="sm"
            disabled={offset + PROPOSALS_PAGE_SIZE >= total}
            onClick={() => patch({ offset: offset + PROPOSALS_PAGE_SIZE })}
          >
            Próxima →
          </Button>
        </div>
      ) : null}

      <Card>
        <CardHeader className="text-sm font-semibold">Ledger dos merges</CardHeader>
        <CardBody className="grid gap-2">
          <p className="text-xs text-(--color-muted)">
            O merge é a operação mais destrutiva do sistema: ele apaga a tag absorvida e reescreve os vínculos. Cada
            linha aqui guarda o estado anterior — tag, vínculos, classificação e grafias — e o desfazer restaura tudo.
          </p>
          {log.isPending ? <Spinner label="Lendo o ledger…" /> : null}
          {log.error ? <ErrorState error={log.error} /> : null}
          {log.data && (log.data.items ?? []).length === 0 ? (
            <EmptyState title="Nenhum merge aplicado ainda" hint="O ledger registra cada tag absorvida, com o antes." />
          ) : null}
          <ul className="divide-y divide-(--color-line) text-xs">
            {(log.data?.items ?? []).map((entry) => (
              <li key={entry.merge_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="min-w-0">
                  <span className="font-medium">{entry.absorbed_name}</span>
                  <span className="text-(--color-muted)"> → {entry.canonical_name}</span>
                  <span className="text-(--color-muted)">
                    {" "}
                    · {formatCount(entry.document_count)} doc(s) · {formatDateTime(entry.changed_at)}
                    {entry.changed_by ? ` · por ${entry.changed_by}` : ""}
                  </span>
                </span>
                {entry.undone_at ? (
                  <Badge tone="neutral">desfeito em {formatDateTime(entry.undone_at)}</Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={undo.isPending}
                    title="Restaura a tag, os vínculos, a classificação e as grafias absorvidas."
                    onClick={() => undo.mutate(entry.merge_id)}
                  >
                    desfazer
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {undo.error ? <ErrorState error={undo.error} /> : null}
          {log.data && log.data.total > MERGE_LOG_PAGE_SIZE ? (
            <p className="text-xs text-(--color-muted)">
              Mostrando os {MERGE_LOG_PAGE_SIZE} mais recentes de {formatCount(log.data.total)}.
            </p>
          ) : null}
        </CardBody>
      </Card>

      <p className="text-xs text-(--color-muted)">
        A quarta subtela do sitemap — stopwords — <strong>não está aqui</strong>: a purga apaga tags e ainda não existe
        rota para ler as stopwords atuais nem preview do que seria apagado. Enquanto isso, uma tela que apaga sem
        mostrar o impacto não entra.
      </p>
    </div>
  );
}

/**
 * One cluster, with the evidence and the two decisions that are possible about it.
 *
 * The preview is a step, not a decoration: ``category_would_be_lost`` is the only warning that the
 * merge would destroy a classification, and it has to be seen **before** the verdict, because
 * approving records an intent that the next suggestion run will not overwrite.
 */
function ProposalCard({
  proposal,
  selected,
  onToggle,
}: {
  proposal: TagMergeProposal;
  selected: boolean;
  onToggle: (checked: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<MergePreview | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["taxonomy", "merge-proposals"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const decide = useMutation({
    mutationFn: (status: "APPROVED" | "REJECTED") =>
      decideMergeProposal(proposal.proposal_id, { status, decided_by: null, note: null }),
    onSuccess: invalidate,
  });

  const dryRun = useMutation({
    mutationFn: () => previewMerge(proposal.proposal_id),
    onSuccess: setPreview,
  });

  const flags = proposal.review_flags ?? [];

  return (
    <Card>
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <Badge tone={PROPOSAL_STATUS_TONE[proposal.status] ?? "neutral"}>
              {labelOf(PROPOSAL_STATUS_LABEL, proposal.status)}
            </Badge>
            <span className="text-sm font-medium">{proposal.canonical_name}</span>
            <Badge tone={MERGE_REASON_TONE[proposal.reason] ?? "neutral"}>
              {labelOf(MERGE_REASON_LABEL, proposal.reason)}
            </Badge>
            <span className="text-xs text-(--color-muted)">{formatCount(proposal.total_documents)} documento(s)</span>
          </span>
          {proposal.status === "APPROVED" ? (
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={selected} onChange={(event) => onToggle(event.target.checked)} />
              incluir no lote
            </label>
          ) : null}
        </div>

        {flags.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {flags.map((flag) => (
              <li key={flag}>
                <Badge tone="warn" title={REVIEW_FLAG_HINT[flag]}>
                  {labelOf(REVIEW_FLAG_LABEL, flag)}
                </Badge>
              </li>
            ))}
          </ul>
        ) : null}

        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {(proposal.members ?? []).map((member) => (
            <li key={member.tag_id} className={member.tag_id === proposal.canonical_id ? "font-medium" : ""}>
              {member.name}
              <span className="text-(--color-muted)"> ({formatCount(member.document_count)})</span>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={dryRun.isPending} onClick={() => dryRun.mutate()}>
            {dryRun.isPending ? "Conferindo…" : "Conferir impacto"}
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={decide.isPending || proposal.status === "APPROVED"}
            onClick={() => decide.mutate("APPROVED")}
          >
            Aprovar
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={decide.isPending || proposal.status === "REJECTED"}
            onClick={() => decide.mutate("REJECTED")}
          >
            Rejeitar
          </Button>
          {proposal.decided_by || proposal.decision_note ? (
            <span className="text-xs text-(--color-muted)">
              {proposal.decided_by ? `por ${proposal.decided_by}` : ""}
              {proposal.decision_note ? ` · ${proposal.decision_note}` : ""}
            </span>
          ) : null}
        </div>

        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
        {decide.error ? <ErrorState error={decide.error} /> : null}

        {preview ? (
          <div className="grid gap-1 rounded-md bg-black/[0.02] p-3 text-xs ring-1 ring-(--color-line)">
            <p className="font-medium">Nada foi escrito ainda. O apply usa este mesmo planejador.</p>
            <p className="text-(--color-muted)">
              {formatCount(preview.documents_updated)} documento(s) atualizado(s) ·{" "}
              {formatCount(preview.links_rewritten)} vínculo(s) reescrito(s) ·{" "}
              {formatCount((preview.tags_deleted ?? []).length)} tag(s) absorvida(s)
            </p>
            <ul className="text-(--color-muted)">
              {(preview.tags_deleted ?? []).map((impact) => (
                <li key={impact.tag_id}>
                  {impact.name} ({formatCount(impact.document_count)} doc
                  {impact.macro_category_id ? `, gaveta ${impact.macro_category_id}` : ""})
                </li>
              ))}
            </ul>
            {(preview.synonyms_created ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                grafias registradas: <code>{(preview.synonyms_created ?? []).join(", ")}</code>
              </p>
            ) : null}
            {(preview.synonyms_repointed ?? []).length > 0 ? (
              <p className="text-(--color-muted)">
                grafias reapontadas: <code>{(preview.synonyms_repointed ?? []).join(", ")}</code>
              </p>
            ) : null}
            {preview.category_would_be_lost ? (
              <p className="rounded bg-(--color-danger)/5 px-2 py-1 text-(--color-danger) ring-1 ring-(--color-danger)/20">
                Esta unificação <strong>apaga uma classificação de assunto</strong>: um dos membros está numa gaveta que
                a canônica não tem.
              </p>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

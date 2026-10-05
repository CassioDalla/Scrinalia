import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  decideHierarchyPlan,
  suggestHierarchyPlans,
  type DescriptionLevel,
  type HierarchyNodePlan,
  type PlanStatus,
} from "@/api/client";
import { queries } from "@/api/queries";
import { MaterialisationPanel } from "@/components/hierarchy/MaterialisationPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { formatCount, formatDateTime } from "@/lib/format";
import {
  PLAN_FLAG_HINT,
  PLAN_FLAG_LABEL,
  PLAN_STATUS_LABEL,
  PLAN_STATUS_TONE,
  labelOf,
} from "@/lib/hierarchy";

const routeApi = getRouteApi("/arranjo/plano");

/**
 * The URL is the state, as in the collection list: the tab, the flag filter and the code search all
 * live in the query string, so an archivist can send a colleague the exact slice of the plan they
 * are arguing about.
 *
 * The search is applied locally because the whole catalogue is ~52 rungs and reading it once is
 * cheaper than a request per keystroke — but it is still the URL that holds it.
 */
export type PlanSearch = { status?: PlanStatus; flag?: string; q?: string };

const STATUSES: PlanStatus[] = ["SUGGESTED", "APPROVED", "REJECTED"];

export function validatePlanSearch(search: Record<string, unknown>): PlanSearch {
  const status = search.status;
  return {
    status: typeof status === "string" && (STATUSES as string[]).includes(status) ? (status as PlanStatus) : undefined,
    flag: typeof search.flag === "string" && search.flag.length > 0 ? search.flag : undefined,
    q: typeof search.q === "string" && search.q.length > 0 ? search.q : undefined,
  };
}

export function PlanRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const plans = useQuery(queries.plans(search.status));
  const vocabulary = useQuery(queries.hierarchyVocabulary());
  const levels = useQuery(queries.levels());

  const suggest = useMutation({
    mutationFn: suggestHierarchyPlans,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["hierarchy", "plans"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    },
  });

  const patch = (changes: Partial<PlanSearch>) => navigate({ to: "/arranjo/plano", search: { ...search, ...changes } });

  const all = plans.data?.items ?? [];
  const term = search.q?.toLowerCase();
  const visible = all.filter((plan) => {
    if (search.flag && !(plan.flags ?? []).includes(search.flag)) return false;
    if (term && !plan.code.toLowerCase().includes(term)) return false;
    return true;
  });

  const statusCounts = plans.data?.status_counts ?? {};
  const total = plans.data?.total ?? 0;
  const flags = vocabulary.data?.plan_flags ?? [];

  return (
    <>
      <PageHeader
        title="Plano de arranjo"
        subtitle={
          plans.data ? (
            <>
              {formatCount(visible.length)} de {formatCount(total)} rungs
              {search.status ? ` · ${labelOf(PLAN_STATUS_LABEL, search.status)}` : ""}
            </>
          ) : (
            "Lendo o catálogo de decisões…"
          )
        }
        actions={
          <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
            {suggest.isPending ? "Propondo…" : "Propor níveis"}
          </Button>
        }
      />

      <div className="flex min-h-0">
        <div className="min-w-0 flex-1 px-6 py-5">
          <p className="mb-4 max-w-3xl text-sm text-(--color-muted)">
            A máquina lê os códigos de referência e propõe as rungs; a decisão é sua. Nada é criado no acervo até a
            materialização — e uma decisão tomada nunca é sobrescrita por uma nova proposta.
          </p>

          {suggest.data ? (
            <p className="mb-4 rounded-md bg-(--color-ok)/5 px-3 py-2 text-xs text-(--color-ok) ring-1 ring-(--color-ok)/25">
              Proposta: {formatCount(suggest.data.created)} rung(s) nova(s), {formatCount(suggest.data.refreshed)}{" "}
              atualizada(s), {formatCount(suggest.data.preserved)} decisão(ões) preservada(s). Total no catálogo:{" "}
              {formatCount(suggest.data.total)}.
            </p>
          ) : null}
          {suggest.error ? <ErrorState error={suggest.error} /> : null}

          <div className="flex flex-wrap items-center gap-2 pb-4">
            <Button size="sm" variant={search.status ? "secondary" : "primary"} onClick={() => patch({ status: undefined })}>
              Todos {plans.data ? `(${formatCount(total)})` : ""}
            </Button>
            {(vocabulary.data?.plan_statuses ?? STATUSES).map((status) => (
              <Button
                key={status}
                size="sm"
                variant={search.status === status ? "primary" : "secondary"}
                onClick={() => patch({ status: status as PlanStatus })}
              >
                {labelOf(PLAN_STATUS_LABEL, status)} ({formatCount(statusCounts[status] ?? 0)})
              </Button>
            ))}
            <Select
              className="w-52"
              value={search.flag ?? ""}
              onChange={(event) => patch({ flag: event.target.value || undefined })}
            >
              <option value="">Todos os avisos</option>
              {flags.map((flag) => (
                <option key={flag} value={flag}>
                  {labelOf(PLAN_FLAG_LABEL, flag)}
                </option>
              ))}
            </Select>
            <Input
              className="max-w-xs"
              placeholder="Filtrar por código…"
              defaultValue={search.q ?? ""}
              onChange={(event) => patch({ q: event.target.value || undefined })}
            />
          </div>

          {plans.error ? <ErrorState error={plans.error} /> : null}
          {plans.isPending ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-28" />
              ))}
            </div>
          ) : null}

          {plans.data && total === 0 ? (
            <EmptyState
              title="O catálogo de decisões está vazio"
              hint="Nenhuma rung foi proposta ainda. A proposta lê os códigos de referência do acervo e escreve as perguntas — nenhum nó é criado na coleção."
              action={
                <Button onClick={() => suggest.mutate()} disabled={suggest.isPending}>
                  Propor níveis
                </Button>
              }
            />
          ) : null}

          {plans.data && total > 0 && visible.length === 0 ? (
            <EmptyState
              title="Nenhuma rung com este filtro"
              hint="Há rungs no catálogo, mas nenhuma casa com o aviso ou o código que você digitou."
              action={
                <Button size="sm" onClick={() => navigate({ to: "/arranjo/plano", search: {} })}>
                  Limpar filtros
                </Button>
              }
            />
          ) : null}

          <ul className="flex flex-col gap-2">
            {visible.map((plan) => (
              <li key={plan.plan_id}>
                <PlanCard plan={plan} levels={levels.data ?? []} allCodes={all.map((item) => item.code)} />
              </li>
            ))}
          </ul>
        </div>

        <aside className="w-[380px] shrink-0 overflow-y-auto border-l border-(--color-line) bg-(--color-surface) px-4 py-5">
          <MaterialisationPanel totalPlans={total} statusCounts={statusCounts} />
        </aside>
      </div>
    </>
  );
}

/**
 * One rung and everything the archivist needs to decide about it.
 *
 * The evidence comes first and the buttons last: the sketch of the screen in the sitemap is explicit
 * that the decision must be taken while looking at `document_count`, the declared levels and the
 * samples, not after scrolling past them.
 */
function PlanCard({
  plan,
  levels,
  allCodes,
}: {
  plan: HierarchyNodePlan;
  levels: DescriptionLevel[];
  allCodes: string[];
}) {
  const queryClient = useQueryClient();
  const [levelId, setLevelId] = useState<number | null>(plan.level_id ?? null);
  const [title, setTitle] = useState(plan.title ?? "");
  const [collapse, setCollapse] = useState(plan.collapse_into_code ?? "");
  const [note, setNote] = useState(plan.decision_note ?? "");

  const decide = useMutation({
    mutationFn: (status: PlanStatus) =>
      decideHierarchyPlan(plan.plan_id, {
        status,
        level_id: levelId,
        title: title || null,
        collapse_into_code: collapse || null,
        note: note || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["hierarchy", "plans"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
    },
  });

  const open = plan.status === "SUGGESTED";
  const canApprove = levelId !== null;
  const flags = plan.flags ?? [];
  const declaredLevels = plan.declared_levels ?? [];
  const samples = plan.sample_description_ids ?? [];

  return (
    <Card>
      <CardBody className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded bg-black/[0.05] px-1.5 py-0.5 text-sm">{plan.code}</code>
          <Badge tone={PLAN_STATUS_TONE[plan.status] ?? "neutral"}>{labelOf(PLAN_STATUS_LABEL, plan.status)}</Badge>
          {flags.map((flag) => (
            <Badge key={flag} tone="neutral" title={PLAN_FLAG_HINT[flag]}>
              {labelOf(PLAN_FLAG_LABEL, flag)}
            </Badge>
          ))}
          {plan.materialised_description_id ? <Badge tone="ok">materializado</Badge> : null}
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-muted)">
          <span>profundidade {plan.depth}</span>
          <span>· pai: {plan.parent_code ?? "raiz"}</span>
          <span>· {formatCount(plan.document_count ?? 0)} descrição(ões)</span>
          <span>· níveis declarados: {declaredLevels.join(", ") || "nenhum"}</span>
        </div>

        {samples.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-(--color-muted)">amostras:</span>
            {samples.map((id) => (
              <Link
                key={id}
                to="/acervo/$descriptionId"
                params={{ descriptionId: id }}
                className="rounded bg-black/[0.05] px-1 hover:underline"
              >
                {id}
              </Link>
            ))}
          </div>
        ) : null}

        {plan.collapse_into_code ? (
          <p className="text-xs text-(--color-accent)">
            Esta rung <strong>é</strong> <code>{plan.collapse_into_code}</code>: o apply segue o vínculo.
          </p>
        ) : null}

        {open ? (
          <div className="mt-1 flex flex-col gap-2 border-t border-(--color-line) pt-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs">
                <span className="text-(--color-muted)">
                  Nível de descrição {flags.includes("ORDINAL_INFERRED") ? "(inferido, não declarado)" : ""}
                </span>
                <Select
                  value={levelId ?? ""}
                  onChange={(event) => setLevelId(event.target.value ? Number(event.target.value) : null)}
                >
                  <option value="">— escolher —</option>
                  {levels.map((level) => (
                    <option key={level.level_id} value={level.level_id}>
                      {level.ordinal}. {level.name}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="text-(--color-muted)">Título do nó</span>
                <Input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder={plan.code}
                  maxLength={300}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="text-(--color-muted)">Fundir em (esta rung é o mesmo nível que…)</span>
                <Input
                  value={collapse}
                  onChange={(event) => setCollapse(event.target.value)}
                  placeholder="código de outra rung"
                  list={`codes-${plan.plan_id}`}
                  maxLength={500}
                />
                <datalist id={`codes-${plan.plan_id}`}>
                  {allCodes
                    .filter((code) => code !== plan.code)
                    .map((code) => (
                      <option key={code} value={code} />
                    ))}
                </datalist>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="text-(--color-muted)">Nota da decisão</span>
                <Input value={note} onChange={(event) => setNote(event.target.value)} />
              </label>
            </div>

            {!canApprove ? (
              <p className="text-xs text-(--color-warn)">
                Aprovar exige escolher o nível: é a decisão que o código não sabe tomar.
              </p>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="primary"
                disabled={!canApprove || decide.isPending}
                onClick={() => decide.mutate("APPROVED")}
              >
                {decide.isPending ? "Salvando…" : "Aprovar"}
              </Button>
              <Button size="sm" variant="danger" disabled={decide.isPending} onClick={() => decide.mutate("REJECTED")}>
                Rejeitar
              </Button>
            </div>
            {decide.error ? <ErrorState error={decide.error} /> : null}
          </div>
        ) : (
          <div className="mt-1 flex flex-wrap items-center gap-3 border-t border-(--color-line) pt-3 text-xs">
            <span className="text-(--color-muted)">
              nível: {plan.level ?? "—"}
              {plan.title ? ` · título: ${plan.title}` : ""}
              {plan.decided_by ? ` · por ${plan.decided_by}` : ""}
              {plan.decided_at ? ` · ${formatDateTime(plan.decided_at)}` : ""}
            </span>
            {plan.decision_note ? <span className="text-(--color-muted)">nota: {plan.decision_note}</span> : null}
            <Button
              size="sm"
              variant="ghost"
              disabled={decide.isPending}
              title="Volta a rung para 'sugerido': a próxima proposta pode atualizar a evidência de novo."
              onClick={() => decide.mutate("SUGGESTED")}
            >
              Reabrir decisão
            </Button>
            {decide.error ? <ErrorState error={decide.error} /> : null}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

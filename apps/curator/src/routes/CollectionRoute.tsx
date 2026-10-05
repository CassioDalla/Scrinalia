import { useQuery } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";

import type { ArchiveReviewStatus, DocumentSearch, FacetCount, SearchMode } from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { formatCount, formatDate, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE, subjectBadge } from "@/lib/format";

const PAGE_SIZE = 25;

/**
 * ``getRouteApi`` instead of importing the route object: the route is declared in ``router.tsx``
 * and the component lives here, and importing one from the other would be a cycle.
 */
const routeApi = getRouteApi("/acervo/lista");


/**
 * The URL is the state.
 *
 * The query-string keys are the API's own parameter names, so there is exactly one vocabulary
 * between the address bar, the request and the contract — no translation table to keep in step.
 * It is also what makes a filtered list shareable and the back button work.
 */
export type CollectionSearch = {
  term?: string;
  mode?: SearchMode;
  typology_id?: number;
  macro_category_id?: number;
  entity_type?: string;
  level_id?: number;
  date_from?: string;
  date_to?: string;
  status?: ArchiveReviewStatus;
  is_anomaly?: boolean;
  offset?: number;
};

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  const text = asString(value);
  if (text === undefined) return undefined;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function asBoolean(value: unknown): boolean | undefined {
  const text = asString(value);
  if (text === undefined) return undefined;
  if (text === "true") return true;
  if (text === "false") return false;
  return undefined;
}

export function validateCollectionSearch(search: Record<string, unknown>): CollectionSearch {
  return {
    term: asString(search.term),
    mode: search.mode === "semantic" ? "semantic" : "lexical",
    typology_id: asNumber(search.typology_id),
    macro_category_id: asNumber(search.macro_category_id),
    entity_type: asString(search.entity_type),
    level_id: asNumber(search.level_id),
    date_from: asString(search.date_from),
    date_to: asString(search.date_to),
    status: asString(search.status) as ArchiveReviewStatus | undefined,
    is_anomaly: asBoolean(search.is_anomaly),
    offset: asNumber(search.offset),
  };
}

function toRequest(search: CollectionSearch): DocumentSearch {
  return { ...search, limit: PAGE_SIZE, offset: search.offset ?? 0 };
}

/** Filters that are set, so the UI can show and clear them as a group. */
function activeFilters(search: CollectionSearch): { key: keyof CollectionSearch; label: string }[] {
  const entries: { key: keyof CollectionSearch; label: string }[] = [];
  if (search.typology_id !== undefined) entries.push({ key: "typology_id", label: `Tipologia #${search.typology_id}` });
  if (search.macro_category_id !== undefined)
    entries.push({ key: "macro_category_id", label: `Assunto #${search.macro_category_id}` });
  if (search.entity_type !== undefined) entries.push({ key: "entity_type", label: `Entidade ${search.entity_type}` });
  if (search.level_id !== undefined) entries.push({ key: "level_id", label: `Nível #${search.level_id}` });
  if (search.status !== undefined)
    entries.push({ key: "status", label: REVIEW_STATUS_LABEL[search.status] ?? search.status });
  if (search.is_anomaly !== undefined)
    entries.push({ key: "is_anomaly", label: search.is_anomaly ? "Somente anomalias" : "Somente sem anomalia" });
  if (search.date_from !== undefined) entries.push({ key: "date_from", label: `De ${search.date_from}` });
  if (search.date_to !== undefined) entries.push({ key: "date_to", label: `Até ${search.date_to}` });
  return entries;
}

function FacetGroup({
  title,
  values,
  selected,
  onSelect,
}: {
  title: string;
  values: FacetCount[] | undefined;
  selected: string | undefined;
  onSelect: (key: string | undefined) => void;
}) {
  if (!values || values.length === 0) return null;
  return (
    <div className="border-b border-(--color-line) px-4 py-3 last:border-b-0">
      <p className="pb-2 text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">{title}</p>
      <ul className="space-y-0.5">
        {values.map((value) => {
          const isSelected = selected === value.key;
          return (
            <li key={value.key}>
              <button
                onClick={() => onSelect(isSelected ? undefined : value.key)}
                aria-pressed={isSelected}
                className={
                  "flex w-full items-center justify-between gap-2 rounded px-1.5 py-1 text-left text-sm transition " +
                  (isSelected
                    ? "bg-(--color-accent)/10 font-medium text-(--color-accent)"
                    : "hover:bg-black/[0.04]")
                }
              >
                <span className="truncate">{value.label}</span>
                <span className="shrink-0 text-xs tabular-nums text-(--color-muted)">{formatCount(value.count)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function CollectionRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const request = toRequest(search);
  const { data, isPending, isFetching, error } = useQuery(queries.documents(request));

  const patch = (changes: Partial<CollectionSearch>) =>
    navigate({
      to: "/acervo/lista",
      search: (previous: CollectionSearch) => ({ ...previous, ...changes, offset: 0 }),
    });

  const facets = data?.facets;
  const total = data?.total ?? 0;
  const offset = search.offset ?? 0;
  const filters = activeFilters(search);

  return (
    <>
      <PageHeader
        title="Acervo"
        subtitle={
          data ? (
            <>
              {formatCount(total)} descrições
              {search.term ? ` para “${search.term}”` : ""}
              {isFetching ? <span className="ml-2 text-xs">atualizando…</span> : null}
            </>
          ) : (
            "Buscando…"
          )
        }
      />

      <div className="flex min-h-0">
        <aside className="w-72 shrink-0 border-r border-(--color-line) bg-(--color-surface)">
          <FacetGroup
            title="Tipologia"
            values={facets?.typology}
            selected={search.typology_id?.toString()}
            onSelect={(key) => patch({ typology_id: key ? Number(key) : undefined })}
          />
          <FacetGroup
            title="Assunto"
            values={facets?.macro_category}
            selected={search.macro_category_id?.toString()}
            onSelect={(key) => patch({ macro_category_id: key ? Number(key) : undefined })}
          />
          <FacetGroup
            title="Tipo de entidade"
            values={facets?.entity_type}
            selected={search.entity_type}
            onSelect={(key) => patch({ entity_type: key })}
          />
          <FacetGroup
            title="Nível de descrição"
            values={facets?.level}
            selected={search.level_id?.toString()}
            onSelect={(key) => patch({ level_id: key ? Number(key) : undefined })}
          />
        </aside>

        <div className="min-w-0 flex-1 px-6 py-5">
          <div className="flex flex-wrap items-center gap-2 pb-4">
            <Input
              defaultValue={search.term ?? ""}
              placeholder="Buscar no acervo…"
              className="max-w-md"
              onKeyDown={(event) => {
                if (event.key === "Enter") patch({ term: event.currentTarget.value || undefined });
              }}
            />
            <Select
              value={search.mode ?? "lexical"}
              onChange={(event) => patch({ mode: event.target.value as SearchMode })}
              className="w-40"
            >
              <option value="lexical">Lexical</option>
              <option value="semantic">Semântica</option>
            </Select>
            <Button onClick={() => patch({ term: undefined, status: undefined, is_anomaly: undefined })}>
              Limpar busca
            </Button>
          </div>

          {/* The honest note the sitemap asks for: the semantic ranking is measured as weak. */}
          {search.mode === "semantic" ? (
            <p className="mb-3 rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
              A busca semântica tem qualidade medida fraca (Hit@10 0.625). Prefira o modo lexical quando
              souber o termo.
            </p>
          ) : null}

          {filters.length > 0 ? (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {filters.map((filter) => (
                <button key={filter.key} onClick={() => patch({ [filter.key]: undefined } as Partial<CollectionSearch>)}>
                  <Badge tone="accent" title="Clique para remover">
                    {filter.label} ✕
                  </Badge>
                </button>
              ))}
            </div>
          ) : null}

          {error ? <ErrorState error={error} /> : null}
          {isPending ? <Spinner /> : null}

          {data && data.items.length === 0 ? (
            <EmptyState
              title="Nenhuma descrição encontrada"
              hint={
                filters.length > 0
                  ? "Há filtros ativos. Remova um deles para ampliar a busca."
                  : "O acervo pode ainda não estar materializado nem revisado — veja a página inicial."
              }
              action={
                filters.length > 0 ? (
                  <Button
                    size="sm"
                    onClick={() =>
                      navigate({
                        to: "/acervo/lista",
                        search: search.term ? { term: search.term, mode: search.mode } : {},
                      })
                    }
                  >
                    Limpar filtros
                  </Button>
                ) : null
              }
            />
          ) : null}

          <ul className="space-y-2">
            {data?.items.map((document) => {
              const subject = subjectBadge(document.macro_categories ?? []);
              return (
                <li key={document.description_id}>
                  <Card className="transition hover:ring-(--color-accent)/40">
                    <CardBody className="flex flex-col gap-2">
                      <div className="flex items-start justify-between gap-3">
                        <Link
                          to="/acervo/$descriptionId"
                          params={{ descriptionId: document.description_id }}
                          className="min-w-0 text-sm font-medium hover:underline"
                        >
                          {document.final_title || document.original_title}
                        </Link>
                        <Badge tone={REVIEW_STATUS_TONE[document.review_status]}>
                          {REVIEW_STATUS_LABEL[document.review_status]}
                        </Badge>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
                        <span>{formatDate(document.document_date)}</span>
                        {document.level ? <span>· {document.level}</span> : null}
                        {document.typology ? <span>· {document.typology}</span> : null}
                        {document.reference_code ? (
                          <code className="rounded bg-black/[0.05] px-1">{document.reference_code}</code>
                        ) : null}
                        {document.is_anomaly ? <Badge tone="warn">anomalia</Badge> : null}
                      </div>

                      {/* Badge rule (Fase 1.5): winner by votes, plus how many drawers it also has. */}
                      {subject ? (
                        <div className="flex items-center gap-2">
                          <Badge tone="accent">{subject.name}</Badge>
                          {subject.others > 0 ? <Badge tone="neutral">+{subject.others}</Badge> : null}
                        </div>
                      ) : null}

                      {document.scope_content ? (
                        <p className="line-clamp-2 text-xs text-(--color-muted)">{document.scope_content}</p>
                      ) : null}
                    </CardBody>
                  </Card>
                </li>
              );
            })}
          </ul>

          {total > PAGE_SIZE ? (
            <div className="flex items-center justify-between pt-4 text-sm">
              <Button
                size="sm"
                disabled={offset === 0}
                onClick={() => patch({ offset: Math.max(0, offset - PAGE_SIZE) })}
              >
                ← Anterior
              </Button>
              <span className="text-xs text-(--color-muted)">
                {formatCount(offset + 1)}–{formatCount(Math.min(offset + PAGE_SIZE, total))} de{" "}
                {formatCount(total)}
              </span>
              <Button
                size="sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => patch({ offset: offset + PAGE_SIZE })}
              >
                Próxima →
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}

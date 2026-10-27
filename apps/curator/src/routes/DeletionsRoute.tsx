import { useQuery } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { queries, DELETIONS_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { formatCount, formatDateTime } from "@/lib/format";
import { ISAD_FIELDS } from "@/lib/isad";
import { asNumber, asString } from "@/lib/search";

const routeApi = getRouteApi("/acervo/excluidas");

/**
 * The ISAD(G) fields first, in the order the dossier shows them.
 *
 * The snapshot is a dump of the table, so it arrives ordered by column definition — ``path``,
 * ``created_at``, ``is_anomaly`` before the title. Reading a record's remains should start with the
 * fields that describe the record.
 */
const SNAPSHOT_FIELD_ORDER = [
  "original_title",
  "final_title",
  // The record in the dossier's own order, read from the one catalogue that names it — a second
  // hand-kept list here would fall behind the next field the archive gains.
  ...ISAD_FIELDS.map((field) => field.name),
  "date_expression",
  "original_url",
  "parent_reference_code",
  "level_id",
  "parent_id",
  "path",
  "summary",
  "review_status",
  "is_published",
];

/**
 * Bookkeeping that a person reading the trail has no use for.
 *
 * ``execution_log`` is the workers' JSONB stamp and would print as a wall of machine keys; the rest of
 * the columns are the record.
 */
const SNAPSHOT_HIDDEN = new Set(["execution_log", "search_vector", "embedding"]);

/** The snapshot's entries, ISAD first, then whatever the model gained afterwards. */
function snapshotEntries(snapshot: Record<string, unknown>): [string, unknown][] {
  const entries = Object.entries(snapshot ?? {}).filter(
    ([field, value]) => !SNAPSHOT_HIDDEN.has(field) && value !== null && value !== "",
  );
  const rank = (field: string) => {
    const index = SNAPSHOT_FIELD_ORDER.indexOf(field);
    return index === -1 ? SNAPSHOT_FIELD_ORDER.length : index;
  };
  return entries.sort(([left], [right]) => rank(left) - rank(right) || left.localeCompare(right));
}

/**
 * The trail of the one destructive write in the curator UI.
 *
 * It exists because a deletion would otherwise leave **nothing**: the revision ledger cascades with
 * the document, so the snapshot the API writes before deleting is the only record of what was removed.
 * The screen is therefore a reading surface with a job — answer "did I delete this?" — and not a
 * recycle bin: nothing here restores anything, and saying so is part of the screen.
 *
 * Search and pagination are **server-side**, unlike the small ledgers of the vocabulary screen: this
 * trail has no ceiling, and a filter that only saw the loaded page would answer "não está aqui" for a
 * record that is.
 */
export type DeletionsSearch = { termo?: string; offset?: number };

export function validateDeletionsSearch(search: Record<string, unknown>): DeletionsSearch {
  const offset = asNumber(search.offset);
  return {
    termo: asString(search.termo),
    offset: offset !== undefined && offset > 0 ? offset : undefined,
  };
}

export function DeletionsRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const offset = search.offset ?? 0;
  const page = useQuery(queries.deletions(search.termo, offset));

  const patch = (changes: Partial<DeletionsSearch>) =>
    navigate({ to: "/acervo/excluidas", search: { ...search, ...changes, offset: changes.offset } });

  const total = page.data?.total ?? 0;
  const items = page.data?.items ?? [];

  return (
    <>
      <PageHeader
        screen="deletions"
        pending={page.isPending}
        status={
          page.data
            ? `${formatCount(total)} item(ns) no histórico de exclusões${search.termo ? ` para “${search.termo}”` : ""}`
            : undefined
        }
      />

      <PageBody>
        <Notice tone="warn">
          Histórico permanente de exclusões.
          Os itens desta lista foram excluídos em definitivo e não podem ser restaurados.
          Esta página preserva os dados originais e o responsável
          pela ação apenas para fins de consulta e auditoria.
        </Notice>

        <div className="flex flex-wrap items-center gap-2">
          <SearchBox value={search.termo} onSearch={(termo) => patch({ termo })} />
          {search.termo ? (
            <Button size="sm" variant="ghost" onClick={() => patch({ termo: undefined })}>
              Limpar busca
            </Button>
          ) : null}
        </div>

        {page.error ? <ErrorState error={page.error} /> : null}
        {page.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-20" />
            ))}
          </div>
        ) : null}

        {page.data && total === 0 ? (
          <EmptyState
            title={search.termo ? `Nenhum item excluído encontrado para “${search.termo}”` : "Nenhum item excluído até o momento"}
            hint={
              search.termo
                ? "Tente pesquisar por outro termo, código de referência ou ID."
                : "O acervo não possui registros de exclusão. Quando um item for removido, o histórico completo de dados aparecerá aqui para consulta."
            }
            action={
              search.termo ? (
                <Button size="sm" onClick={() => patch({ termo: undefined })}>
                  Limpar busca
                </Button>
              ) : null
            }
          />
        ) : null}

        <ul className="grid gap-2">
          {items.map((entry) => (
            <li key={entry.deletion_id}>
              <Card>
                <CardBody className="grid gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium">{entry.title}</span>
                      {entry.level_name ? <Badge tone="neutral">{entry.level_name}</Badge> : null}
                      <Badge tone="neutral" title="ID do registro">
                        {entry.description_id}
                      </Badge>
                    </div>
                    <span className="text-xs text-(--color-muted)">{formatDateTime(entry.deleted_at)}</span>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-muted)">
                    {entry.reference_code ? (
                      <code className="rounded bg-black/[0.05] px-1">{entry.reference_code}</code>
                    ) : (
                      <span>Sem código de referência</span>
                    )}
                    <span>· Excluído por {entry.deleted_by ?? "usuário não identificado"}</span>
                    {entry.children_count > 0 ? (
                      <span>· Continha {formatCount(entry.children_count)} item(ns) vinculado(s)</span>
                    ) : null}
                  </div>

                  {entry.note ? <p className="text-xs italic text-(--color-muted)">{entry.note}</p> : null}

                  {/*
                    The snapshot is what makes the trail useful: it is the only surviving copy of the
                    description, and it is read on demand because a ledger of full ISAD(G) records would
                    otherwise be a wall of text.
                  */}
                  <details className="text-xs">
                    <summary className="cursor-pointer text-(--color-muted)">
                      Ver dados arquivados do item ({formatCount(snapshotEntries(entry.snapshot ?? {}).length)} campo(s))
                    </summary>
                    <ul className="mt-2 grid gap-1">
                      {snapshotEntries(entry.snapshot ?? {}).map(([field, value]) => (
                        <li key={field} className="grid gap-0.5">
                          <code className="text-[10px] text-(--color-muted)">{field}</code>
                          <span className="break-words">{typeof value === "string" ? value : JSON.stringify(value)}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>

        {total > DELETIONS_PAGE_SIZE ? (
          <div className="flex items-center justify-between text-sm">
            <Button
              size="sm"
              disabled={offset === 0}
              onClick={() => navigate({ to: "/acervo/excluidas", search: { ...search, offset: Math.max(0, offset - DELETIONS_PAGE_SIZE) } })}
            >
              ← Anterior
            </Button>
            <span className="text-xs text-(--color-muted)">
              {formatCount(offset + 1)}–{formatCount(Math.min(offset + DELETIONS_PAGE_SIZE, total))} de{" "}
              {formatCount(total)}
            </span>
            <Button
              size="sm"
              disabled={offset + DELETIONS_PAGE_SIZE >= total}
              onClick={() =>
                navigate({ to: "/acervo/excluidas", search: { ...search, offset: offset + DELETIONS_PAGE_SIZE } })
              }
            >
              Próxima →
            </Button>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}

/**
 * The search box fires while the archivist types, as in the collection list.
 *
 * The term goes into the URL, which is what issues the request: one source of truth, and the back
 * button works.
 */
function SearchBox({ value, onSearch }: { value: string | undefined; onSearch: (term: string | undefined) => void }) {
  const fromUrl = value ?? "";
  const [term, setTerm] = useState(fromUrl);
  const [seen, setSeen] = useState(fromUrl);

  if (fromUrl !== seen) {
    setSeen(fromUrl);
    setTerm(fromUrl);
  }

  useEffect(() => {
    const handle = setTimeout(() => {
      const next = term.trim();
      if (fromUrl === next) return;
      onSearch(next.length > 0 ? next : undefined);
    }, 250);
    return () => clearTimeout(handle);
  }, [term, fromUrl, onSearch]);

  return (
    <Input
      value={term}
      className="max-w-md"
      placeholder="Buscar por código, título ou ID..."
      onChange={(event) => setTerm(event.target.value)}
    />
  );
}

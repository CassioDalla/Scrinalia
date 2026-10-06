import { useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";

/**
 * A ledger: a growing list that has to stay searchable.
 *
 * Every audit trail in the system is a list that only ever grows — absorbed tags, banned terms,
 * synonyms, revisions, materialised runs — and every one of them was rendered as one long column.
 * Finding the term a colleague mentions meant scrolling with the browser's own search, and the
 * screen had no way to say "there is more below" once the list outgrew the page.
 *
 * The search is **local** on purpose: these lists come from the API whole (a couple of hundred rows
 * today) and a request per keystroke would buy nothing. The compensating rule is that the screen must
 * never lie about what it is showing, so the footer always states how many rows exist in total and
 * how many are drawn — the same honesty the paginated screens keep with their "1–20 de 888".
 *
 * The term is **not** in the URL, unlike the filters of the collection list: a ledger search is a
 * spot check ("where is that term?"), not a view somebody sends to a colleague, and six routes
 * gaining a search key each is a cost with no reader.
 */
export function LedgerList<T>({
  items,
  termOf,
  renderItem,
  keyOf,
  searchPlaceholder = "buscar no histórico…",
  nounSingular,
  nounPlural,
  emptyTitle,
  emptyHint,
  /** How many rows are drawn before the archivist asks for the rest. */
  pageSize = 20,
}: {
  items: T[];
  /** The texts a term is matched against; several because a ledger row has a name on each side. */
  termOf: (item: T) => string[];
  renderItem: (item: T) => ReactNode;
  keyOf: (item: T) => string | number;
  searchPlaceholder?: string;
  nounSingular: string;
  nounPlural: string;
  emptyTitle: string;
  emptyHint?: ReactNode;
  pageSize?: number;
}) {
  const [term, setTerm] = useState("");
  const [limit, setLimit] = useState(pageSize);

  const needle = normalize(term);
  const matches = useMemo(() => {
    if (needle.length === 0) return items;
    return items.filter((item) => termOf(item).some((text) => normalize(text).includes(needle)));
  }, [items, needle, termOf]);

  const visible = matches.slice(0, limit);
  const hidden = matches.length - visible.length;
  const searching = needle.length > 0;

  return (
    <div className="grid gap-2">
      <Input
        value={term}
        placeholder={searchPlaceholder}
        className="max-w-xs"
        onChange={(event) => {
          setTerm(event.target.value);
          // A new question starts from the top of its own answer; keeping the window where the
          // previous term left it would show an empty page over a list that does match.
          setLimit(pageSize);
        }}
      />

      {items.length === 0 ? (
        <EmptyState title={emptyTitle} hint={emptyHint} />
      ) : matches.length === 0 ? (
        <EmptyState
          title={`Nenhum resultado para “${term}”`}
          hint={`Há ${items.length} ${items.length === 1 ? nounSingular : nounPlural} no histórico, mas nenhum casa com o termo.`}
        />
      ) : (
        <>
          <ul className="divide-y divide-(--color-line) text-xs">
            {visible.map((item) => (
              <li key={keyOf(item)}>{renderItem(item)}</li>
            ))}
          </ul>
          {hidden > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="ghost" onClick={() => setLimit((current) => current + pageSize)}>
                ver mais {Math.min(hidden, pageSize)}
              </Button>
              <span className="text-xs text-(--color-muted)">
                mostrando {visible.length} de {matches.length}
                {searching ? ` que casam com “${term}”` : ""} ({items.length} no total)
              </span>
            </div>
          ) : (
            <p className="text-xs text-(--color-muted)">
              {searching
                ? `${matches.length} de ${items.length} ${items.length === 1 ? nounSingular : nounPlural}`
                : `${items.length} ${items.length === 1 ? nounSingular : nounPlural}`}
            </p>
          )}
        </>
      )}
    </div>
  );
}

/** Case- and accent-insensitive, so “serie” finds “Série” — the archivist types on a Brazilian keyboard. */
function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

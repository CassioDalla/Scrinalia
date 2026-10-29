import { useQuery } from "@tanstack/react-query";

import type { DocumentSearch } from "@/api/client";
import { queries } from "@/api/queries";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { formatCount, formatDate, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";
import { useCopy } from "@/i18n/context";

/**
 * The descriptions one object holds, paged, read through the collection search.
 *
 * Shared by the two catalogues that show a weight and then have to be able to show what it counts: a
 * subject category (``macro_category_id``) and a named entity (``entity_id``). The read is
 * ``GET /api/v1/documents`` with the same filter the list screen uses, so the number on the card and
 * the ``total`` here are one definition counted twice — ``test_category_documents.py`` and
 * ``test_entity_documents.py`` fail when the two stop agreeing.
 *
 * No new route was invented for this and none should be: the filter already existed, and a second read
 * of the same rows is the defect the taxonomy rule file names first.
 *
 * The empty state is the **caller's**, because "nenhuma descrição nesta categoria" and "nenhuma
 * descrição carrega este nome" are different sentences about different objects and a shared component
 * that guessed one would be wrong half the time.
 */
export function DescriptionExpansion({
  params,
  pageSize,
  offset,
  onPage,
  onPreview,
  empty,
}: {
  /** The filter that defines the set. Paging belongs to this component, so it is not accepted here. */
  params: Omit<DocumentSearch, "limit" | "offset">;
  pageSize: number;
  offset: number;
  onPage: (offset: number) => void;
  onPreview: (descriptionId: string) => void;
  empty: { title: string; hint: string };
}) {
  const messages = useCopy();
  const documents = useQuery(queries.documents({ ...params, limit: pageSize, offset }));

  const items = documents.data?.items ?? [];
  const total = documents.data?.total ?? 0;

  if (documents.error) return <ErrorState error={documents.error} />;
  if (documents.isPending) return <Spinner label={messages.common.readingDescriptions} />;

  if (items.length === 0) return <EmptyState title={empty.title} hint={empty.hint} />;

  return (
    <div className="grid gap-2">
      <ul className="divide-y divide-(--color-line)">
        {items.map((document) => (
          <li key={document.description_id}>
            <button
              type="button"
              onClick={() => onPreview(document.description_id)}
              className="flex w-full flex-col gap-1 px-1 py-2 text-left hover:bg-black/[0.03]"
            >
              <span className="flex items-start justify-between gap-3">
                <span className="min-w-0 text-sm font-medium">
                  {document.final_title || document.original_title}
                </span>
                <Badge tone={REVIEW_STATUS_TONE[document.review_status]}>
                  {REVIEW_STATUS_LABEL[document.review_status]}
                </Badge>
              </span>
              <span className="flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
                <span>{formatDate(document.document_date)}</span>
                {document.level ? <span>· {document.level}</span> : null}
                {document.typology ? <span>· {document.typology}</span> : null}
                {document.reference_code ? (
                  <code className="rounded bg-black/[0.05] px-1">{document.reference_code}</code>
                ) : null}
                {document.is_anomaly ? <Badge tone="warn">anomalia</Badge> : null}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {total > pageSize ? (
        <div className="flex items-center justify-between pt-2 text-sm">
          <Button size="sm" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - pageSize))}>
            ← Anterior
          </Button>
          <span className="text-xs text-(--color-muted)">
            {messages.common.range.replace("{from}", formatCount(offset + 1)).replace("{to}", formatCount(Math.min(offset + pageSize, total))).replace("{total}", formatCount(total))}
          </span>
          <Button size="sm" disabled={offset + pageSize >= total} onClick={() => onPage(offset + pageSize)}>
            {messages.common.next}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

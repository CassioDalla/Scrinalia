import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { type DocumentSummary } from "@/api/client";
import { queries } from "@/api/queries";
import { Badge } from "@/components/ui/Badge";
import { ErrorState, Spinner } from "@/components/ui/Feedback";
import { SidePanel, SidePanelClose } from "@/components/ui/SidePanel";
import { formatDate, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";

/**
 * The read-only preview: enough of the record to recognise it, and nothing that writes.
 *
 * It **reads the description again** instead of rendering the row the click came from. That is one
 * request, and it is what makes the panel honest against the URL: the id can arrive from a shared
 * link, and the row it names may not be on the page the colleague's offset points at. A panel that
 * only worked when the list happened to carry the row would answer an empty box for a link that is
 * correct.
 *
 * ``editTab`` is the caller's decision and not a default, because "Editar" goes to the tab of the
 * dossier that actually edits what was being looked at: the drawer of subject tags is the
 * **description** tab for a category, while an entity's links are added and removed on the
 * **assuntos** tab. A default here would send half the callers to a tab that cannot do the edit.
 */
export function DescriptionPreview({
  descriptionId,
  editTab,
  onClose,
}: {
  descriptionId: string;
  /** The dossier tab "Editar" opens: ``descricao`` for a category, ``assuntos`` for an entity. */
  editTab: string;
  onClose: () => void;
}) {
  const document = useQuery(queries.document(descriptionId));
  const title = document.data ? document.data.final_title || document.data.original_title : descriptionId;

  return (
    <SidePanel
      label={`Prévia de ${title}`}
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-(--color-muted)">Nada aqui altera a descrição.</span>
          <Link
            to="/acervo/$descriptionId"
            params={{ descriptionId }}
            search={{ aba: editTab }}
            className="rounded bg-(--color-brand) px-3 py-1.5 text-sm font-medium text-white"
          >
            Editar
          </Link>
        </div>
      }
    >
      <div className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 text-base font-semibold">{title}</h2>
          <SidePanelClose onClose={onClose} />
        </div>

        {document.error ? <ErrorState error={document.error} /> : null}
        {document.isPending ? <Spinner label="Lendo a descrição…" /> : null}

        {document.data ? <DescriptionPreviewBody document={document.data} /> : null}
      </div>
    </SidePanel>
  );
}

/** The fields the panel shows, each one only when the description carries it. */
function DescriptionPreviewBody({ document }: { document: DocumentSummary }) {
  const tags = document.tags ?? [];

  return (
    <div className="grid gap-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={REVIEW_STATUS_TONE[document.review_status]}>
          {REVIEW_STATUS_LABEL[document.review_status]}
        </Badge>
        {document.is_published ? <Badge tone="ok">publicada</Badge> : <Badge tone="neutral">não publicada</Badge>}
        {document.is_anomaly ? <Badge tone="warn">anomalia</Badge> : null}
      </div>

      <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1 text-xs">
        {document.reference_code ? (
          <>
            <dt className="text-(--color-muted)">Código de Referência</dt>
            <dd>
              <code>{document.reference_code}</code>
            </dd>
          </>
        ) : null}
        <dt className="text-(--color-muted)">Data</dt>
        <dd>{formatDate(document.document_date)}</dd>
        <dt className="text-(--color-muted)">Nível</dt>
        <dd>{document.level ?? "—"}</dd>
        <dt className="text-(--color-muted)">Tipologia</dt>
        <dd>{document.typology ?? "—"}</dd>
        <dt className="text-(--color-muted)">Arranjo</dt>
        <dd className="break-all">{document.path ?? "—"}</dd>
      </dl>

      {document.scope_content ? (
        <p className="line-clamp-4 text-xs text-(--color-muted)">{document.scope_content}</p>
      ) : null}

      <div className="grid gap-1">
        <p className="text-xs font-medium text-(--color-muted)">Tags e Categoria</p>
        {tags.length === 0 ? (
          <p className="text-xs text-(--color-muted)">Nenhuma tag nesta descrição.</p>
        ) : (
          <ul className="grid gap-1">
            {tags.map((tag) => (
              <li key={tag.tag_id} className="flex flex-wrap items-center gap-2 text-xs">
                <span className="truncate">{tag.name}</span>
                {tag.macro_category_name ? (
                  <Badge tone="accent">{tag.macro_category_name}</Badge>
                ) : (
                  <Badge tone="neutral" title="Esta tag ainda não tem categoria">
                    sem categoria
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

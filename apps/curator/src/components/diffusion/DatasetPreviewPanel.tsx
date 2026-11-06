import type { DatasetPreview } from "@/api/client";
import { Badge } from "@/components/ui/Badge";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { formatCount } from "@/lib/format";

/**
 * What an export run would write, without writing it (ADR 0024).
 *
 * The panel is the operator's dry run: the record count, the exact size of each enabled format, the
 * removals since the current snapshot and the sentence that says why a run would refuse. It is a
 * read of the package the adapter would produce — the button does not enqueue anything, and the
 * panel says so in its own hint, because a preview that looks like a run is a preview the operator
 * stops trusting.
 */
export function DatasetPreviewPanel({ preview }: { preview: DatasetPreview }) {
  const messages = useCopy();
  const copy = messages.pages.diffusion;

  return (
    <div className="grid gap-2 rounded-md bg-black/5 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={preview.ready ? "ok" : "warn"}>
          {preview.ready ? copy.previewReady : copy.previewNotReady}
        </Badge>
        {preview.unchanged ? <span className="text-(--color-muted)">{copy.previewUnchanged}</span> : null}
      </div>

      <p>{fill(copy.previewRecords, { count: formatCount(preview.record_count) })}</p>
      {preview.reason ? <p className="text-(--color-danger)">{preview.reason}</p> : null}
      <p className="text-(--color-muted)">
        {copy.previewDestination}: {preview.destination ?? copy.none}
      </p>

      <ul className="grid gap-0.5">
        {preview.artifacts.map((artifact) => (
          <li key={artifact.format}>
            {artifact.path} · {formatBytes(artifact.bytes)}
          </li>
        ))}
      </ul>

      {preview.removals.length > 0 ? (
        <div className="grid gap-0.5">
          <p>{fill(copy.previewRemovals, { count: formatCount(preview.removals.length) })}</p>
          <p className="break-words text-(--color-muted)">{preview.removals.slice(0, 10).join(", ")}</p>
        </div>
      ) : (
        <p className="text-(--color-muted)">{copy.previewNoRemovals}</p>
      )}

      <p className="text-(--color-muted)">{copy.previewHint}</p>
    </div>
  );
}

/** A byte count for the operator; the panel is not a place for a third significant digit. */
function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} kB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

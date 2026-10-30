import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  applyPublication,
  previewPublication,
  type DiffusionChannel,
  type PublicationAction,
  type PublicationBatch,
  type PublicationMode,
  type PublicationPreview,
  type PublicationRequest,
} from "@/api/client";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { SidePanel } from "@/components/ui/SidePanel";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { formatCount } from "@/lib/format";

/** What the page asks the panel to do; the channels are the operator's configured ones. */
export type PublicationPanelRequest = {
  action: PublicationAction;
  mode: PublicationMode;
  nodeId?: string;
  descriptionIds?: string[];
  includeDescendants?: boolean;
  /** Pre-selected channels: a record's own channels for "keep private", one for a scope action. */
  channels?: string[];
};

const ACTION_COPY = {
  PUBLISH: "publish",
  EXCLUDE: "exclude",
  REVOKE: "revoke",
  UNEXCLUDE: "unexclude",
} as const;

/**
 * The panel that writes: choose the channels, preview, confirm.
 *
 * The preview is a **read**, and the panel does not let the confirm run before one: the token it
 * answers is the one the apply echoes, so a set that changed between the two calls refuses instead
 * of publishing something the curator did not see. The panel closes only after the batch, and the
 * result it shows is the ledger's own counts.
 */
export function PublicationPanel({
  request,
  channels,
  onClose,
}: {
  request: PublicationPanelRequest;
  channels: DiffusionChannel[];
  onClose: () => void;
}) {
  const messages = useCopy();
  const copy = messages.pages.publication;
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string[]>(
    request.channels ?? channels.map((channel) => channel.code),
  );
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<PublicationPreview | null>(null);
  const [batch, setBatch] = useState<PublicationBatch | null>(null);

  const body: PublicationRequest = {
    action: request.action,
    channel_codes: selected,
    mode: request.mode,
    node_id: request.nodeId ?? null,
    description_ids: request.descriptionIds ?? [],
    include_descendants: request.includeDescendants ?? true,
    note: note.trim() ? note.trim() : null,
  };

  const previewMutation = useMutation({
    mutationFn: () => previewPublication(body),
    onSuccess: (data) => {
      setPreview(data);
      setBatch(null);
    },
  });
  const applyMutation = useMutation({
    mutationFn: () => applyPublication({ request: body, token: preview?.token ?? "" }),
    onSuccess: (data) => {
      setBatch(data);
      queryClient.invalidateQueries({ queryKey: ["diffusion"] });
    },
  });

  const title = copy.preview[ACTION_COPY[request.action]];
  const toggle = (code: string) =>
    setSelected((current) =>
      current.includes(code) ? current.filter((item) => item !== code) : [...current, code],
    );

  return (
    <SidePanel
      label={title}
      onClose={onClose}
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={onClose}>
            {batch ? copy.actions.close : copy.preview.cancel}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => previewMutation.mutate()}
            disabled={selected.length === 0 || previewMutation.isPending || batch !== null}
          >
            {copy.preview.preview}
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={() => applyMutation.mutate()}
            disabled={preview === null || batch !== null || applyMutation.isPending}
          >
            {applyMutation.isPending ? copy.preview.confirming : copy.preview.confirm}
          </Button>
        </div>
      }
    >
      <div className="grid gap-3">
        <h2 className="text-base font-semibold">{title}</h2>

        <fieldset className="grid gap-1">
          <legend className="text-xs font-medium text-(--color-muted)">{copy.preview.channels}</legend>
          {channels.length === 0 ? (
            <p className="text-xs text-(--color-warn)">{copy.preview.noChannel}</p>
          ) : (
            channels.map((channel) => (
              <label key={channel.code} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={selected.includes(channel.code)}
                  onChange={() => toggle(channel.code)}
                />
                <span>{channel.label}</span>
                <span className="text-xs text-(--color-muted)">{channel.code}</span>
              </label>
            ))
          )}
        </fieldset>

        <Field label={copy.preview.note} htmlFor="publication-note">
          <Textarea id="publication-note" rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>

        {previewMutation.error ? <ErrorState error={previewMutation.error} /> : null}
        {applyMutation.error ? <ErrorState error={applyMutation.error} /> : null}

        {preview ? (
          <div className="grid gap-2">
            {(preview.channels ?? []).map((channel) => (
              <div key={channel.code} className="rounded-md p-2 ring-1 ring-(--color-line)">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={channel.actionable ? "accent" : "neutral"}>{channel.label}</Badge>
                  <span className="text-xs text-(--color-muted)">
                    {fill(copy.preview.eligible, { count: formatCount(channel.eligible) })}
                  </span>
                  {!channel.actionable ? (
                    <span className="text-xs text-(--color-warn)">{copy.preview.blocked}</span>
                  ) : null}
                </div>
                {(channel.sample ?? []).length > 0 ? (
                  <ul className="mt-1 grid gap-0.5">
                    {(channel.sample ?? []).map((sample) => (
                      <li key={sample.description_id} className="truncate text-xs" title={sample.title}>
                        {sample.title}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <p className="mt-1 text-[11px] text-(--color-muted)">
                  {fill(copy.preview.skipped, {
                    notApproved: formatCount(channel.skipped?.not_approved ?? 0),
                    covered: formatCount(channel.skipped?.already_covered ?? 0),
                    excluded: formatCount(channel.skipped?.excluded ?? 0),
                    notCovered: formatCount(channel.skipped?.not_covered ?? 0),
                  })}
                </p>
              </div>
            ))}
            {preview.total_eligible === 0 && (preview.channels ?? []).every((channel) => channel.actionable) ? (
              <Notice tone="neutral">{copy.preview.nothing}</Notice>
            ) : null}
          </div>
        ) : null}

        {batch ? (
          <Notice tone="ok">
            {fill(copy.preview.done, {
              id: String(batch.batch_id),
              applied: formatCount(batch.applied_count),
              skipped: formatCount(batch.skipped_count),
            })}
          </Notice>
        ) : null}
      </div>
    </SidePanel>
  );
}

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useId, useState } from "react";

import {
  previewDiffusionChannel,
  triggerDiffusionRun,
  updateDiffusionChannel,
  type DiffusionChannel,
} from "@/api/client";
import { DatasetPreviewPanel } from "@/components/diffusion/DatasetPreviewPanel";
import { configSummary, DiffusionConfigForm } from "@/components/diffusion/DiffusionConfigForm";
import { DiffusionScheduleForm } from "@/components/diffusion/DiffusionScheduleForm";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/Feedback";
import { Notice } from "@/components/ui/Notice";
import { PanelToggle } from "@/components/ui/PanelToggle";
import { useCopy } from "@/i18n/context";
import { fill, stringMap } from "@/i18n/maps";
import { formatDateTime } from "@/lib/format";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/system";

/** The two capabilities, named the way the operator reads them. */
const CAPABILITY_LABEL = stringMap((m) => ({
  LIVE: m.pages.diffusion.capabilityLive,
  EXPORT: m.pages.diffusion.capabilityExport,
}));

/**
 * One configured channel: its lifecycle, its configuration and — for an export — its agenda.
 *
 * The card is **always expanded**, unlike an origin's. Its whole body is a summary line and a form
 * the operator asked for, so a collapsed card would hide the configuration they just saved; the
 * actions reveal the form inline and the region carries the `id` the toggle names.
 *
 * `LIVE` and `EXPORT` are not two screens: the capability decides what the card offers, so the
 * dataset adapter (#214) arrives as a registry entry and this file learns nothing. A `LIVE` channel
 * has no run and no agenda; an `EXPORT` one shows the agenda, the last run, the dry-run preview and
 * the enqueue action of the run ledger (#212).
 */
export function DiffusionChannelCard({
  channel,
  canOperate,
}: {
  channel: DiffusionChannel;
  canOperate: boolean;
}) {
  const messages = useCopy();
  const [panel, setPanel] = useState<"none" | "config" | "schedule" | "preview">("none");
  const configId = useId();
  const scheduleId = useId();
  const previewId = useId();
  const preview = useMutation({ mutationFn: () => previewDiffusionChannel(channel.code) });
  const live = channel.capability === "LIVE";
  const siteUrl =
    live && channel.enabled && typeof (channel.config ?? {}).public_base_url === "string"
      ? String((channel.config ?? {}).public_base_url)
      : null;

  const toggle = (next: "config" | "schedule" | "preview") => {
    const opening = panel !== next;
    setPanel(opening ? next : "none");
    if (opening && next === "preview") preview.mutate();
  };

  return (
    <Card>
      <CardBody className="grid gap-3">
        <div className="grid gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{channel.label}</span>
            <Badge tone="neutral">{CAPABILITY_LABEL[channel.capability]}</Badge>
            <Badge tone={channel.enabled ? "ok" : "neutral"}>
              {channel.enabled ? messages.pages.diffusion.activeBadge : messages.pages.diffusion.pausedBadge}
            </Badge>
          </div>
          <p className="text-xs text-(--color-muted)">{channel.description}</p>
          <p className="text-xs text-(--color-muted)">
            {live
              ? messages.pages.diffusion.capabilityLiveHint
              : messages.pages.diffusion.capabilityExportHint}
          </p>
          <p className="text-xs text-(--color-muted)">{configSummary(channel)}</p>
        </div>

        {!live ? (
          <div className="grid gap-0.5 text-xs text-(--color-muted)">
            <span>
              {messages.pages.diffusion.schedule}:{" "}
              {channel.schedule?.cron
                ? fill(messages.pages.diffusion.nextRun, {
                    tz: channel.schedule.timezone ?? "",
                    when: formatDateTime(channel.schedule.next_run_at),
                  })
                : messages.pages.diffusion.noSchedule}
            </span>
            <span className="flex flex-wrap items-center gap-1">
              {messages.pages.diffusion.lastRun}:{" "}
              {channel.last_run_id == null ? (
                messages.pages.diffusion.none
              ) : (
                <Link
                  to="/sistema/workers"
                  search={{ aba: "execucoes", channel: channel.code }}
                  className="underline"
                >
                  #{channel.last_run_id}
                </Link>
              )}
              {channel.last_run_status ? (
                <Badge tone={RUN_STATUS_TONE[channel.last_run_status]}>
                  {RUN_STATUS_LABEL[channel.last_run_status]}
                </Badge>
              ) : null}
              {channel.last_run_at ? <span>· {formatDateTime(channel.last_run_at)}</span> : null}
            </span>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          {canOperate ? (
            <>
              <PanelToggle
                label={messages.pages.diffusion.editConfig}
                active={panel === "config"}
                controls={configId}
                onSelect={() => toggle("config")}
              />
              {!live ? (
                <PanelToggle
                  label={messages.pages.diffusion.scheduleTab}
                  active={panel === "schedule"}
                  controls={scheduleId}
                  onSelect={() => toggle("schedule")}
                />
              ) : null}
              {!live ? (
                <PanelToggle
                  label={
                    preview.isPending ? messages.pages.diffusion.previewing : messages.pages.diffusion.preview
                  }
                  active={panel === "preview"}
                  controls={previewId}
                  onSelect={() => toggle("preview")}
                />
              ) : null}
              {siteUrl ? <SiteLink href={siteUrl} /> : null}
              {!live ? <RunNowButton channel={channel} /> : null}
              <LifecycleButton channel={channel} />
            </>
          ) : (
            <>
              {siteUrl ? <SiteLink href={siteUrl} /> : null}
              <p className="text-xs text-(--color-muted)">{messages.pages.diffusion.operatorOnly}</p>
            </>
          )}
        </div>

        {live ? <Notice tone="neutral">{messages.pages.diffusion.publicSiteNote}</Notice> : null}

        {canOperate && panel === "config" ? (
          <div id={configId}>
            <DiffusionConfigForm channel={channel} mode="edit" />
          </div>
        ) : null}
        {canOperate && !live && panel === "schedule" ? (
          <div id={scheduleId}>
            <DiffusionScheduleForm channel={channel} />
          </div>
        ) : null}
        {canOperate && !live && panel === "preview" ? (
          <div id={previewId}>
            {preview.error ? (
              <ErrorState error={preview.error} />
            ) : preview.data ? (
              <DatasetPreviewPanel preview={preview.data} />
            ) : (
              <p className="text-xs text-(--color-muted)">{messages.pages.diffusion.previewing}</p>
            )}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

/** The public address, when there is one and the channel is enabled; a link, not a false "published". */
function SiteLink({ href }: { href: string }) {
  const messages = useCopy();
  return (
    <a
      className="text-xs font-medium text-(--color-accent) underline"
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      {messages.pages.diffusion.viewSite}
    </a>
  );
}

/**
 * Enqueues one export run of this channel, and says why the button is not available.
 *
 * A paused channel does not export, and a channel with a run in flight keeps its slot (the partial
 * unique index): the button says which of the two it is instead of offering a click that would
 * answer 409 or 422. A queued answer is shown with its id, because "nothing happened" is not a
 * state the operator should have to guess.
 */
function RunNowButton({ channel }: { channel: DiffusionChannel }) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const run = useMutation({
    mutationFn: () => triggerDiffusionRun(channel.code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["diffusion", "channels"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "runs"] });
    },
  });

  const paused = !channel.enabled;
  const active = channel.active_run_id != null;

  return (
    <div className="grid gap-1">
      <Button
        size="sm"
        variant="primary"
        disabled={paused || active || run.isPending}
        onClick={() => run.mutate()}
      >
        {paused
          ? messages.pages.diffusion.pausedChannel
          : active
            ? messages.pages.diffusion.alreadyRunning
            : run.isPending
              ? messages.pages.diffusion.enqueuing
              : messages.pages.diffusion.enqueueRun}
      </Button>
      {run.data ? (
        <span className="text-xs text-(--color-muted)">
          {fill(messages.pages.diffusion.queuedLine, { id: String(run.data.run_id) })}
        </span>
      ) : null}
      {run.error ? <ErrorState error={run.error} /> : null}
    </div>
  );
}

/** Pausing is the lifecycle, not a removal: the row, the configuration and the agenda stay. */
function LifecycleButton({ channel }: { channel: DiffusionChannel }) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => updateDiffusionChannel(channel.code, { enabled: !channel.enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["diffusion", "channels"] });
    },
  });

  return (
    <div className="grid gap-1">
      <Button
        size="sm"
        variant={channel.enabled ? "ghost" : "secondary"}
        disabled={toggle.isPending}
        onClick={() => toggle.mutate()}
      >
        {toggle.isPending
          ? messages.pages.diffusion.saving
          : channel.enabled
            ? messages.pages.diffusion.pause
            : messages.pages.diffusion.reactivate}
      </Button>
      {toggle.error ? <ErrorState error={toggle.error} /> : null}
    </div>
  );
}

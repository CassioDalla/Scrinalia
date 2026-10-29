import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  deleteDiffusionSchedule,
  saveDiffusionSchedule,
  type DiffusionChannel,
} from "@/api/client";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";
import { useCopy } from "@/i18n/context";

/**
 * The agenda of an `EXPORT` channel: a five-field cron in an explicit IANA zone.
 *
 * A `LIVE` channel has no run — the public site is read on every request — so this form is offered
 * only where the capability says there is a run to schedule, and the API refuses it on the other
 * side too (`PUT /channels/{code}/schedule` answers 422 for `LIVE`). The zone is required in
 * practice: the API falls back to `DEFAULT_TIMEZONE`, but a cron without a zone is the classic way
 * a scheduled export runs at the wrong hour after a deploy.
 */
export function DiffusionScheduleForm({ channel }: { channel: DiffusionChannel }) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const [cron, setCron] = useState(channel.schedule?.cron ?? "0 2 * * *");
  const [timezone, setTimezone] = useState(channel.schedule?.timezone ?? "America/Sao_Paulo");

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["diffusion", "channels"] });
  };

  const save = useMutation({
    mutationFn: () =>
      saveDiffusionSchedule(channel.code, { cron: cron.trim(), timezone: timezone.trim() || null }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: () => deleteDiffusionSchedule(channel.code),
    onSuccess: invalidate,
  });

  return (
    <div className="grid gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <p className="text-xs text-(--color-muted)">{messages.pages.diffusion.cronHint}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={messages.pages.diffusion.scheduleField}>
          <Input value={cron} onChange={(event) => setCron(event.target.value)} placeholder="0 2 * * *" />
        </Field>
        <Field label={messages.pages.diffusion.timezoneField}>
          <Input
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="America/Sao_Paulo"
          />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={save.isPending || cron.trim().length === 0}
          onClick={() => save.mutate()}
        >
          {save.isPending ? messages.pages.diffusion.saving : messages.pages.diffusion.saveSchedule}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={remove.isPending || !channel.schedule}
          onClick={() => remove.mutate()}
        >
          {messages.pages.diffusion.removeSchedule}
        </Button>
      </div>
      {save.error ? <ErrorState error={save.error} /> : null}
      {remove.error ? <ErrorState error={remove.error} /> : null}
    </div>
  );
}
